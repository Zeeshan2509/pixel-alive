import asyncio
import os
import re
from playwright.async_api import async_playwright

async def ping_buzzheavier_links(links_file="links.txt"):
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
    
    async with async_playwright() as p:
        # Run headless for GitHub Actions
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(accept_downloads=True)
        page = await context.new_page()
        
        for url in urls:
            print(f"\n🌐 Navigating to {url}...")
            try:
                await page.goto(url)
                
                print("⏳ Waiting for Cloudflare and download button...")
                await page.wait_for_selector(".download-btn", timeout=60000)
                
                print("⬇️ Clicking download button...")
                try:
                    async with page.expect_download(timeout=60000) as download_info:
                        await page.locator(".download-btn").first.click()
                        
                    download = await download_info.value
                    print(f"📥 Started stream for: {download.suggested_filename}...")
                    
                    # Wait 15 seconds to register as an active download on their servers
                    print("⏳ Pinging stream for 15 seconds...")
                    await asyncio.sleep(15)
                    
                    # Cancel it to save bandwidth and storage
                    await download.cancel()
                    print(f"✅ Successfully pinged and cancelled: {download.suggested_filename}")
                except Exception as e:
                    print(f"❌ Failed to ping {url}: {e}")
                    
            except Exception as e:
                print(f"❌ Error processing {url}: {e}")
                
        await browser.close()
        print("\n🎉 All Buzzheavier links pinged successfully!")

if __name__ == "__main__":
    asyncio.run(ping_buzzheavier_links("links.txt"))
