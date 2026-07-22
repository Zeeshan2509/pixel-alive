import os
import time
from curl_cffi import requests

def ping_buzzheavier_links(links_file="../links.txt"):
    print(f"🚀 Starting Buzzheavier Keep-Alive Pinger...")
    
    # 1. Read Buzzheavier links from links.txt
    urls = []
    if os.path.exists(links_file):
        with open(links_file, "r", encoding="utf-8") as f:
            for line in f:
                if "buzzheavier.com" in line:
                    # Extract just the URL part
                    parts = line.split("http")
                    if len(parts) > 1:
                        url = "http" + parts[1].strip()
                        urls.append(url)
    
    if not urls:
        print(f"⚠️ No Buzzheavier links found in {links_file}.")
        return

    print(f"📋 Found {len(urls)} Buzzheavier links to ping.")
    
    session = requests.Session(impersonate="chrome")
    
    for url in urls:
        print(f"\n🌐 Pinging {url}...")
        try:
            # 1. Get the initial page to set cookies
            session.get(url)
            
            # 2. Hit the HTMX download endpoint
            file_id = url.rstrip("/").split("/")[-1]
            download_url = f"https://buzzheavier.com/{file_id}/download"
            
            resp = session.get(
                download_url,
                headers={"HX-Request": "true", "HX-Current-URL": url},
                allow_redirects=False
            )
            
            redirect_url = resp.headers.get("HX-Redirect") or resp.headers.get("hx-redirect")
            if redirect_url:
                if redirect_url.startswith("/"):
                    redirect_url = f"https://buzzheavier.com{redirect_url}"
                
                print(f"🔗 Found direct URL. Starting ping stream...")
                
                cookie_str = "; ".join([f"{k}={v}" for k, v in session.cookies.items()])
                headers = {"Referer": url}
                if cookie_str:
                    headers["Cookie"] = cookie_str
                    
                # 3. Stream for 15 seconds to register as a download
                start_time = time.time()
                bytes_downloaded = 0
                
                stream_resp = session.get(redirect_url, stream=True, headers=headers)
                
                for chunk in stream_resp.iter_content(chunk_size=1024 * 1024):
                    bytes_downloaded += len(chunk)
                    if time.time() - start_time > 15:
                        print(f"✅ Pinged successfully for 15s ({bytes_downloaded / 1024 / 1024:.2f} MB). Cancelling stream.")
                        stream_resp.close()
                        break
                        
            else:
                print(f"❌ Failed to get direct URL for {url}. Server returned: {resp.text[:100]}")
                
        except Exception as e:
            print(f"❌ Error processing {url}: {e}")
            
    print("\n🎉 All Buzzheavier links pinged successfully!")

if __name__ == "__main__":
    target = "../links.txt" if os.path.exists("../links.txt") else "links.txt"
    ping_buzzheavier_links(target)
