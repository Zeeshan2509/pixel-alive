import os
import re
import shutil
import subprocess
import time
import random
import requests
import jsbeautifier.unpackers.packer as packer

# ═══════════════════════════════════════════════════════
#  Configuration
# ═══════════════════════════════════════════════════════
IA_ACCESS = "18C8XEk4nnoXoDIB"
IA_SECRET = "3AgwOiH5JtmAXECF"
IA_IDENTIFIER = "got-hls-yemaha4899"
MIN_FILE_SIZE_MB = 500
PROGRESS_FILE = "Progress.txt"
# Stop processing 15 minutes before the GitHub Actions 6-hour limit
MAX_RUNTIME_SECONDS = 5 * 60 * 60 + 45 * 60  # 5h 45m

START_TIME = time.time()


def elapsed_minutes():
    return (time.time() - START_TIME) / 60


def time_remaining():
    return MAX_RUNTIME_SECONDS - (time.time() - START_TIME)


def should_stop():
    """Returns True if we're getting close to the 6-hour GitHub Actions limit."""
    return time.time() - START_TIME >= MAX_RUNTIME_SECONDS


# ═══════════════════════════════════════════════════════
#  Progress Tracking
# ═══════════════════════════════════════════════════════
def load_progress():
    """Load already-completed episodes from Progress.txt"""
    done = set()
    if os.path.exists(PROGRESS_FILE):
        with open(PROGRESS_FILE, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    done.add(line)
    return done


def save_progress(entry):
    """Append a completed episode entry to Progress.txt"""
    with open(PROGRESS_FILE, "a", encoding="utf-8") as f:
        f.write(entry + "\n")
    print(f"📝 Progress saved: {entry}")


def commit_progress():
    """Commit Progress.txt back to the repo so the next run picks up where we left off."""
    try:
        subprocess.run(["git", "config", "user.name", "github-actions[bot]"], check=True, capture_output=True)
        subprocess.run(["git", "config", "user.email", "github-actions[bot]@users.noreply.github.com"], check=True, capture_output=True)
        subprocess.run(["git", "add", PROGRESS_FILE], check=True, capture_output=True)
        subprocess.run(["git", "commit", "-m", "Update Progress.txt [skip ci]"], check=True, capture_output=True)
        subprocess.run(["git", "push"], check=True, capture_output=True)
        print("📤 Progress.txt committed and pushed to repo.")
    except subprocess.CalledProcessError as e:
        print(f"⚠️  Could not commit Progress.txt: {e}")


# ═══════════════════════════════════════════════════════
#  Mixdrop CDN Extraction
# ═══════════════════════════════════════════════════════
def extract_mixdrop_cdn(url):
    url = url.replace("/f/", "/e/")
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/115.0.0.0 Safari/537.36"
    }
    html = None
    max_retries = 3
    for attempt in range(max_retries):
        try:
            time.sleep(random.uniform(0.5, 1.5))
            response = requests.get(url, headers=headers, timeout=30)
            response.raise_for_status()
            html = response.text
            break
        except requests.exceptions.HTTPError:
            if response.status_code == 429:
                wait_time = 10 * (attempt + 1)
                print(f"  ⚠️  Rate limited. Waiting {wait_time}s... ({attempt+1}/{max_retries})")
                time.sleep(wait_time)
                if attempt == max_retries - 1:
                    return None
            else:
                return None
        except Exception:
            return None

    if not html:
        return None

    try:
        start_idx = html.find('eval(function(p,a,c,k,e,d)')
        if start_idx == -1:
            return None
        end_idx = html.find(".split('|'),0,{}))", start_idx)
        if end_idx == -1:
            return None
        packed_js = html[start_idx:end_idx + 20]
        if packer.detect(packed_js):
            unpacked_js = packer.unpack(packed_js)
            wurl_match = re.search(r'(?:MDCore\.wurl|wurl)="(.*?)"', unpacked_js)
            if wurl_match:
                cdn_url = wurl_match.group(1)
                if cdn_url.startswith("//"):
                    cdn_url = "https:" + cdn_url
                return cdn_url
    except Exception:
        pass
    return None


# ═══════════════════════════════════════════════════════
#  Parse links.txt → Build Full Episode List
# ═══════════════════════════════════════════════════════
def parse_all_episodes(links_file="links.txt"):
    """
    Returns a list of dicts:
    [
        {"season": "1", "ep_code": "E01", "title": "Winter Is Coming", "url": "https://..."},
        ...
    ]
    Only parses Mixdrop section.
    """
    episodes = []
    in_mixdrop = False
    current_season = None

    with open(links_file, "r", encoding="utf-8") as f:
        for line in f:
            line_str = line.strip()
            if not line_str:
                continue

            # Detect section headers
            section_match = re.match(r'^\s*(Buzzheavier|Mixdrop|Gofile|Pixeldrain)\s*$', line_str, re.IGNORECASE)
            if section_match:
                in_mixdrop = section_match.group(1).lower() == 'mixdrop'
                continue

            if not in_mixdrop:
                continue

            # Skip decorators
            if re.match(r'^[=\-]+$', line_str):
                continue

            # Season header
            season_match = re.search(r'Season\s+(\d+)', line_str, re.IGNORECASE)
            if season_match:
                current_season = season_match.group(1)
                continue

            if not current_season:
                continue

            # Episode line: "E01 Winter Is Coming: https://mixdrop.top/f/..."
            match = re.search(r"(https?://(?:www\.)?(?:mixdrop\.(?:co|top)|miiiixdrop\.net)/[ef]/[a-zA-Z0-9]+)", line_str)
            if match:
                mixdrop_url = match.group(1)
                raw_title = line_str.split("http")[0].strip().rstrip(':').strip()

                # Extract episode code like E01, E02
                ep_match = re.match(r'(E\d+)\s+(.*)', raw_title)
                if ep_match:
                    ep_code = ep_match.group(1)
                    ep_name = ep_match.group(2)
                else:
                    ep_code = ""
                    ep_name = raw_title

                # Clean filename chars
                clean_title = re.sub(r'[\\/*?:"<>|]', "", raw_title)

                episodes.append({
                    "season": current_season,
                    "ep_code": ep_code,
                    "ep_name": ep_name,
                    "title": clean_title,
                    "url": mixdrop_url,
                    "progress_key": f"S{current_season.zfill(2)} {ep_code} {ep_name}"
                })

    return episodes


# ═══════════════════════════════════════════════════════
#  Download a Single Episode
# ═══════════════════════════════════════════════════════
def download_episode(episode, work_dir):
    """Download one episode to work_dir, return the file path."""
    os.makedirs(work_dir, exist_ok=True)

    print(f"  🔗 Resolving CDN link...")
    cdn_url = extract_mixdrop_cdn(episode["url"])
    if not cdn_url:
        print(f"  ❌ Failed to resolve CDN for {episode['title']}")
        return None

    filename = f"{episode['title']}.mkv"
    filepath = os.path.join(work_dir, filename)

    aria2_list = os.path.join(work_dir, "aria2_input.txt")
    with open(aria2_list, "w", encoding="utf-8") as f:
        f.write(f"{cdn_url}\n")
        f.write(f"  dir={work_dir}\n")
        f.write(f"  out={filename}\n")
        f.write("  header=Referer: https://mixdrop.co/\n")
        f.write("  header=User-Agent: Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/115.0.0.0 Safari/537.36\n")

    print(f"  📥 Downloading: {filename}")
    cmd = [
        "aria2c", "-c", "-i", aria2_list, "-s", "16", "-x", "16",
        "--content-disposition-default-utf8=true", "--min-split-size=1M"
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)

    if result.returncode != 0:
        print(f"  ❌ Download failed: {result.stderr[:200]}")
        return None

    # Validate size
    if not os.path.exists(filepath):
        print(f"  ❌ File not found after download: {filepath}")
        return None

    size_mb = os.path.getsize(filepath) / (1024 * 1024)
    print(f"  📄 Size: {size_mb:.0f} MB")
    if size_mb < MIN_FILE_SIZE_MB:
        print(f"  ❌ File too small ({size_mb:.0f}MB < {MIN_FILE_SIZE_MB}MB). Corrupted download.")
        return None

    return filepath


# ═══════════════════════════════════════════════════════
#  FFmpeg: Extract Subtitles + HLS Transcode
# ═══════════════════════════════════════════════════════
def process_episode(filepath, season, episode_title, output_base):
    """
    Transcode a single episode into 5 HLS resolutions and extract subtitles.
    output_base = the Season X folder (e.g., /tmp/Season 1)
    """
    filename_no_ext = os.path.splitext(os.path.basename(filepath))[0]

    resolutions = {
        "1080p": {"scale": "1920:1080", "bitrate": "5000k", "maxrate": "5500k", "bufsize": "10000k"},
        "720p":  {"scale": "1280:720",  "bitrate": "2800k", "maxrate": "3000k", "bufsize": "5600k"},
        "480p":  {"scale": "854:480",   "bitrate": "1400k", "maxrate": "1600k", "bufsize": "2800k"},
        "360p":  {"scale": "640:360",   "bitrate": "800k",  "maxrate": "900k",  "bufsize": "1600k"},
        "240p":  {"scale": "426:240",   "bitrate": "400k",  "maxrate": "450k",  "bufsize": "800k"},
    }

    # Create output dirs
    sub_dir = os.path.join(output_base, f"Season {season} (Subtitles)")
    os.makedirs(sub_dir, exist_ok=True)
    for res in resolutions:
        os.makedirs(os.path.join(output_base, f"Season {season} ({res})"), exist_ok=True)

    # 1. Extract subtitles
    print(f"  📝 Extracting subtitles...")
    sub1 = os.path.join(sub_dir, f"{filename_no_ext}.srt")
    sub2 = os.path.join(sub_dir, f"{filename_no_ext}_track2.srt")
    subprocess.run(["ffmpeg", "-y", "-i", filepath, "-map", "0:s:0?", sub1], capture_output=True)
    subprocess.run(["ffmpeg", "-y", "-i", filepath, "-map", "0:s:1?", sub2], capture_output=True)
    for s in [sub1, sub2]:
        if os.path.exists(s) and os.path.getsize(s) == 0:
            os.remove(s)

    # 2. HLS transcoding — all 5 resolutions in PARALLEL
    print(f"  🎬 Transcoding 5 resolutions in parallel...")
    procs = []
    for res, s in resolutions.items():
        out_dir = os.path.join(output_base, f"Season {season} ({res})")
        out_m3u8 = os.path.join(out_dir, f"{filename_no_ext}.m3u8")

        cmd = [
            "ffmpeg", "-y", "-i", filepath,
            "-vf", f"scale={s['scale']}",
            "-c:v", "libx264",
            "-preset", "ultrafast",
            "-threads", "0",
            "-b:v", s["bitrate"], "-maxrate", s["maxrate"], "-bufsize", s["bufsize"],
            "-c:a", "aac", "-b:a", "128k",
            "-hls_time", "6", "-hls_playlist_type", "vod",
            "-hls_segment_filename", os.path.join(out_dir, f"{filename_no_ext}_%03d.ts"),
            out_m3u8
        ]
        proc = subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        procs.append((res, proc))

    # Wait for all
    for res, proc in procs:
        proc.wait()
        status = "✅" if proc.returncode == 0 else "❌"
        print(f"    {status} {res}")

    return True


# ═══════════════════════════════════════════════════════
#  Upload to Internet Archive
# ═══════════════════════════════════════════════════════
def upload_to_ia(output_base, season):
    """Upload the processed season folder to Internet Archive."""
    print(f"  ☁️  Uploading to Internet Archive...")

    # Configure IA CLI
    subprocess.run(
        ["ia", "configure", "--access-key", IA_ACCESS, "--secret-key", IA_SECRET],
        check=True, capture_output=True
    )

    cmd = [
        "ia", "upload", IA_IDENTIFIER, output_base,
        "--metadata=title:Thrones",
        "--metadata=mediatype:data",
        "--no-derive"
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)

    if result.returncode == 0:
        print(f"  ✅ Upload complete!")
        return True
    else:
        print(f"  ❌ Upload failed: {result.stderr[:200]}")
        return False


# ═══════════════════════════════════════════════════════
#  Main Pipeline
# ═══════════════════════════════════════════════════════
def main():
    print("=" * 60)
    print("  🎬 GOT HLS PIPELINE — GitHub Actions Auto-Runner")
    print("=" * 60)

    # 1. Parse all episodes
    episodes = parse_all_episodes("links.txt")
    print(f"📋 Total episodes found across all seasons: {len(episodes)}")

    # 2. Load progress
    done = load_progress()
    if done:
        print(f"♻️  Already completed {len(done)} episodes. Resuming...")

    # 3. Filter out completed episodes
    remaining = [ep for ep in episodes if ep["progress_key"] not in done]
    print(f"📦 Remaining episodes to process: {len(remaining)}")

    if not remaining:
        print("🎉 ALL EPISODES COMPLETE! Nothing left to process.")
        return

    episodes_done_this_run = 0
    work_dir = "/tmp/work"
    output_base = "/tmp/output"

    for ep in remaining:
        # Check time limit
        if should_stop():
            print(f"\n⏰ Approaching 6-hour limit ({elapsed_minutes():.0f} min elapsed). Stopping gracefully.")
            break

        season = ep["season"]
        print(f"\n{'━' * 60}")
        print(f"🎬 S{season.zfill(2)} {ep['ep_code']} {ep['ep_name']}")
        print(f"   Time elapsed: {elapsed_minutes():.0f} min | Remaining budget: {time_remaining()/60:.0f} min")
        print(f"{'━' * 60}")

        # Clean work directory for each episode
        if os.path.exists(work_dir):
            shutil.rmtree(work_dir)
        if os.path.exists(output_base):
            shutil.rmtree(output_base)

        # Step 1: Download
        filepath = download_episode(ep, work_dir)
        if not filepath:
            print(f"  ⏭️  Skipping {ep['progress_key']} due to download failure.")
            continue

        # Step 2: FFmpeg transcode
        success = process_episode(filepath, season, ep["title"], output_base)
        if not success:
            print(f"  ⏭️  Skipping {ep['progress_key']} due to transcode failure.")
            continue

        # Step 3: Upload to IA
        uploaded = upload_to_ia(output_base, season)
        if not uploaded:
            print(f"  ⏭️  Skipping {ep['progress_key']} due to upload failure.")
            continue

        # Step 4: Cleanup & save progress
        print(f"  🧹 Cleaning up downloaded files...")
        shutil.rmtree(work_dir, ignore_errors=True)
        shutil.rmtree(output_base, ignore_errors=True)

        save_progress(ep["progress_key"])
        episodes_done_this_run += 1

        print(f"  🎉 Done: {ep['progress_key']}")

    # Final commit of progress
    print(f"\n{'=' * 60}")
    print(f"📊 This run completed {episodes_done_this_run} episode(s) in {elapsed_minutes():.0f} minutes.")
    commit_progress()

    remaining_count = len(remaining) - episodes_done_this_run
    if remaining_count > 0:
        print(f"📦 {remaining_count} episode(s) remaining. They will be processed in the next run.")
    else:
        print("🎉 ALL EPISODES COMPLETE!")


if __name__ == "__main__":
    main()
