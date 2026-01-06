

import streamlit as st
import pandas as pd
import requests
from bs4 import BeautifulSoup
from google import genai
import json
import time

# --- 1. PAGE CONFIG ---
st.set_page_config(page_title="AI SEO Index Checker", layout="wide", page_icon="🔍")

st.title("🔍 Bulk AI Index Checker & Auditor")
st.markdown("Check index status in bulk and use **Gemini 2.0** to diagnose non-indexed pages.")

# --- 2. SIDEBAR (API KEYS) ---
with st.sidebar:
    st.header("Settings")
    serper_key = st.text_input("Serper API Key", type="password")
    gemini_key = st.text_input("Gemini API Key", type="password")
    st.info("Your keys are not stored and are only used for this session.")
    st.markdown("---")
    # st.write("Developed by: AI Dev Team")

# --- 3. CORE LOGIC ---
def check_index_bulk(urls, api_key):
    endpoint = "https://google.serper.dev/search"
    headers = {'X-API-KEY': api_key, 'Content-Type': 'application/json'}
    
    # --- CONFIGURATION ---
    BATCH_SIZE = 20  # Keep this safely under 30 to prevent timeouts
    indexed_map = {}
    
    # Loop through URLs in chunks of 20
    for i in range(0, len(urls), BATCH_SIZE):
        batch_urls = urls[i : i + BATCH_SIZE]
        
        # Prepare payload for this specific batch
        payload = [{"q": f'"{u.strip()}"'} for u in batch_urls]
        
        try:
            response = requests.post(endpoint, headers=headers, json=payload, timeout=30) # Increased timeout
            
            # Check if API returned an error (e.g., 403 Forbidden, 429 Too Many Requests)
            if response.status_code != 200:
                print(f"Batch failed with status {response.status_code}: {response.text}")
                # Mark this specific batch as False, but allow others to continue
                for u in batch_urls:
                    indexed_map[u] = False 
                continue

            results = response.json()
            
            # Map results for this batch
            for j, res in enumerate(results):
                # Handle cases where result list might be shorter than batch (rare error)
                if j >= len(batch_urls): 
                    break
                    
                url = batch_urls[j]
                
                # Check organic results
                is_found = any(url.strip().rstrip('/') in item.get('link', '').rstrip('/') 
                               for item in res.get('organic', []))
                
                indexed_map[url] = is_found
                
        except Exception as e:
            print(f"Error checking batch {i}: {e}")
            # If a batch fails, mark only those URLs as False
            for u in batch_urls:
                indexed_map[u] = False
        
        # Optional: Sleep briefly between batches to be safe with rate limits
        time.sleep(1)

    return indexed_map


# def get_ai_diagnosis(url, gemini_client):
#     try:
#         res = requests.get(url, headers={'User-Agent': 'Mozilla/5.0'}, timeout=5)
#         soup = BeautifulSoup(res.text, 'html.parser')
#         content = f"Title: {soup.title.string if soup.title else 'N/A'} | Text: {soup.get_text()[:1000]}"
        
#         prompt = f"Analyze this URL: {url}\nPage Content: {content}\nProvide 1 short reason why Google might NOT index this page."
#         response = gemini_client.models.generate_content(model="gemini-2.5-flash", contents=prompt)
#         return response.text.strip()
#     except:
#         return "Failed to crawl page content."
def get_ai_diagnosis(url, gemini_client):
    # 1. Use "Real" Browser Headers to avoid being blocked
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.5",
        "Referer": "https://www.google.com/"
    }

    try:
        # 2. Increased timeout to 15s (5s is too short for some sites)
        res = requests.get(url, headers=headers, timeout=15)
        
        # 3. Check if the site blocked us (403/401) or failed (500)
        if res.status_code != 200:
            return f"Site blocked the crawler (Status Code: {res.status_code})."

        # 4. Parse content
        soup = BeautifulSoup(res.text, 'html.parser')
        
        # Safety check: if soup.title is None, use URL as title
        title = soup.title.string.strip() if soup.title and soup.title.string else url
        
        # Clean text: remove script/style tags to give Gemini clean data
        for script in soup(["script", "style"]):
            script.extract()
            
        page_text = soup.get_text(separator=' ', strip=True)[:1500] # Limit to 1500 chars
        
        content = f"Title: {title}\nPage Text Snippet: {page_text}"
        
        # 5. Send to Gemini
        prompt = (
            f"Analyze this web page for SEO indexing issues.\n"
            f"URL: {url}\n"
            f"Content Extracted:\n{content}\n\n"
            f"Task: The page is NOT indexed by Google. Based on the content above, "
            f"give 1 likely technical or content reason (e.g., 'Thin content', 'Under construction', 'Login wall', 'Technical error')."
            f"Keep it under 15 words."
        )
        
        response = gemini_client.models.generate_content(model="gemini-3-flash-preview", contents=prompt)
        return response.text.strip()

    except requests.exceptions.Timeout:
        return "Error: Connection timed out (Site is slow)."
    except requests.exceptions.ConnectionError:
        return "Error: Connection refused (Bot protection)."
    except Exception as e:
        return f"Error: {str(e)}"
# --- 4. UI INPUTS ---
url_input = st.text_area("Enter URLs (one per line, up to 20 for trial)", height=150)
urls = [u.strip() for u in url_input.split('\n') if u.strip()]

if st.button("🚀 Start Bulk Audit"):
    if not serper_key or not gemini_key:
        st.error("Please enter both API keys in the sidebar.")
    elif not urls:
        st.warning("Please enter at least one URL.")
    else:
        # Initialize Gemini
        client = genai.Client(api_key=gemini_key)
        
        # UI Feedback
        progress_bar = st.progress(0)
        status_text = st.empty()
        
        # Step A: Bulk Index Check
        status_text.text("Checking index status on Google...")
        index_results = check_index_bulk(urls, serper_key)
        progress_bar.progress(30)
        
        final_data = []
        
        # Step B: AI Audit for Non-indexed
        total = len(urls)
        for i, url in enumerate(urls):
            is_indexed = index_results.get(url, False)
            diag = None
            
            if not is_indexed:
                status_text.text(f"Auditing with AI: {url}")
                diag = get_ai_diagnosis(url, client)
                # Rate limit safety
                time.sleep(2) 
            
            final_data.append({
                "URL": url,
                "Indexed": "✅ Yes" if is_indexed else "❌ No",
                "AI Diagnosis": diag if diag else "N/A (Indexed)"
            })
            
            # Update progress
            progress_val = 30 + int((i + 1) / total * 70)
            progress_bar.progress(progress_val)

        status_text.success("Audit Complete!")
        
        # --- 5. RESULTS DISPLAY ---
        df = pd.DataFrame(final_data)
        st.dataframe(df, use_container_width=True)

        # Metrics
        indexed_count = len(df[df['Indexed'] == "✅ Yes"])
        col1, col2 = st.columns(2)
        col1.metric("Indexed", indexed_count)
        col2.metric("Not Indexed", total - indexed_count)

        # Export Options
        st.markdown("### Export Results")
        csv = df.to_csv(index=False).encode('utf-8')
        json_data = json.dumps(final_data, indent=4)
        
        c1, c2 = st.columns(2)
        c1.download_button("Download CSV", csv, "seo_audit.csv", "text/csv")
        c2.download_button("Download JSON", json_data, "seo_audit.json", "application/json")