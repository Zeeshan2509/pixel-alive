import asyncio
import os
from playwright.async_api import async_playwright

async def ping_mixdrop_links(links_file="../links.txt"):
    print(f"🚀 Starting Mixdrop Keep-Alive Pinger...")
    
    # 1. Read Mixdrop links from links.txt
    urls = []
    if os.path.exists(links_file):
        with open(links_file, "r", encoding="utf-8") as f:
            for line in f:
                if "mixdrop" in line.lower() or "miiiixdrop" in line.lower():
                    parts = line.split("http")
                    if len(parts) > 1:
                        url = "http" + parts[1].strip()
                        urls.append(url)
    
    if not urls:
        print(f"⚠️ No Mixdrop links found in {links_file}.")
        return

    print(f"📋 Found {len(urls)} Mixdrop links to ping.")
    
    async with async_playwright() as p:
        # Run headless for GitHub Actions
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(accept_downloads=True)
        page = await context.new_page()
        
        for url in urls:
            # Make sure it's the download page
            if not url.endswith("?download"):
                url += "?download"
                
            print(f"\n🌐 Navigating to {url}...")
            try:
                await page.goto(url)
                
                print("⏳ Waiting for initial download button...")
                await page.wait_for_selector(".btn3", timeout=30000)
                
                print("⬇️ Clicking button to trigger 3s timer...")
                await page.locator(".btn3").first.click()
                
                print("⏳ Waiting 5 seconds for timer to finish...")
                await asyncio.sleep(5)
                
                print("⬇️ Clicking button again to start download stream...")
                try:
                    async with page.expect_download(timeout=60000) as download_info:
                        await page.locator(".btn3").first.click()
                        
                    download = await download_info.value
                    print(f"📥 Started stream for: {download.suggested_filename}...")
                    
                    print("⏳ Pinging stream for 15 seconds...")
                    await asyncio.sleep(15)
                    
                    await download.cancel()
                    print(f"✅ Successfully pinged and cancelled: {download.suggested_filename}")
                except Exception as e:
                    print(f"❌ Failed to intercept stream for {url}: {e}")
                    
            except Exception as e:
                print(f"❌ Error processing {url}: {e}")
                
        await browser.close()
        print("\n🎉 All Mixdrop links pinged successfully!")

if __name__ == "__main__":
    # Look for links.txt in the parent directory assuming this script is in Automation/
    target = "../links.txt" if os.path.exists("../links.txt") else "links.txt"
    asyncio.run(ping_mixdrop_links(target))
