import logging

class NewsAnalyzer:
    """Integrates NewsScraper sentiment scores per stock and aggregates sector news."""

    def __init__(self, news_scraper=None):
        if news_scraper is None:
            from data.news_scraper import NewsScraper
            self.scraper = NewsScraper()
        else:
            self.scraper = news_scraper
        self.sectors = ["IT", "Banking", "Pharma", "Auto", "Energy", "Metals", "FMCG"]
        logging.info("NewsAnalyzer initialized")

    def filter_credible_news(self, news_data: list) -> list:
        """Filter articles based on freshness and credibility."""
        from datetime import datetime, timezone
        filtered = []
        trusted_sources = ["moneycontrol", "economic times", "bse", "nse", "et markets"]
        
        now = datetime.now(timezone.utc)
        for article in news_data:
            # Check source credibility
            source = article.get("source", "unknown").lower()
            credibility_boost = 1.2 if any(ts in source for ts in trusted_sources) else 1.0
            
            # Check freshness
            ts_str = article.get("timestamp")
            fresh = True
            if ts_str:
                try:
                    dt = datetime.fromisoformat(ts_str.replace('Z', '+00:00'))
                    age = now - dt
                    # Exclude articles older than 24 hours
                    if age.total_seconds() > 86400:
                        fresh = False
                except Exception:
                    pass
            
            if fresh:
                article["credibility_multiplier"] = credibility_boost
                filtered.append(article)
                
        return filtered

    def analyze(self, news_data: list, watchlist: list = None) -> dict:
        """Analyze sentiment for watchlist stocks based on news data."""
        from config import OLLAMA_BASE_URL, OLLAMA_API_KEY, NSE_WATCHLIST
        if watchlist is None:
            watchlist = NSE_WATCHLIST

        # 1. Freshness and Credibility Filtering
        filtered_news = self.filter_credible_news(news_data)
        logging.info(f"Filtered {len(news_data)} articles down to {len(filtered_news)} fresh & credible articles.")

        # 2. Determine which stocks actually have news events to trigger LLM
        llm_trigger_list = []
        neutral_results = {}
        
        for symbol in watchlist:
            plain = symbol.replace('.NS', '').replace('.BO', '').lower()
            # Simple keyword check to see if stock is mentioned in any fresh article
            mentions = [art for art in filtered_news if plain in art.get("headline", "").lower() or plain in art.get("summary", "").lower()]
            
            if mentions:
                llm_trigger_list.append(symbol)
            else:
                # Bypass LLM and assign neutral score (50) directly
                neutral_results[symbol] = {
                    "sentiment_score": 50,
                    "sentiment": "NEUTRAL",
                    "relevant_headlines": [],
                    "catalyst_strength": "NONE"
                }

        logging.info(f"Intelligent News Filter: {len(llm_trigger_list)} stocks triggered LLM scan; {len(neutral_results)} stocks bypassed.")

        if not llm_trigger_list:
            return neutral_results

        # 3. Run LLM on the triggered watchlist
        ollama_ok = True if OLLAMA_API_KEY else self._check_ollama_alive(OLLAMA_BASE_URL)
        if ollama_ok:
            logging.info("Using AI news sentiment analysis for triggered watchlist.")
            results = self._analyze_with_ollama_batched(filtered_news, llm_trigger_list)
            if results:
                # Combine results
                results.update(neutral_results)
                return results
            logging.warning("Ollama returned empty results — falling back to keyword engine.")

        # Fallback keyword engine for triggered stocks
        results = {}
        for symbol in llm_trigger_list:
            plain = symbol.replace('.NS', '').replace('.BO', '')
            results[symbol] = self.scraper.score_news_sentiment(filtered_news, plain)
        
        results.update(neutral_results)
        return results

    def _check_ollama_alive(self, base_url: str) -> bool:
        """Quick health-check: is Ollama server responding?"""
        import requests
        try:
            r = requests.get(f"{base_url.rstrip('/')}/api/tags", timeout=5)
            return r.status_code == 200
        except Exception:
            return False

    def _analyze_with_ollama_batched(self, news_data: list, watchlist: list) -> dict:
        """Run Ollama analysis in batches of 20 stocks to avoid context overflow."""
        BATCH_SIZE = 20
        all_results = {}
        batches = [watchlist[i:i+BATCH_SIZE] for i in range(0, len(watchlist), BATCH_SIZE)]
        for batch in batches:
            batch_result = self._analyze_with_ollama(news_data, batch)
            if batch_result:
                all_results.update(batch_result)
            else:
                # If Ollama fails mid-way, fall back for this batch
                for symbol in batch:
                    plain = symbol.replace('.NS', '')
                    all_results[symbol] = self.scraper.score_news_sentiment(news_data, plain)
        return all_results

    def _analyze_with_ollama(self, news_data: list, watchlist: list) -> dict:
        """Run Ollama sentiment analysis for a batch of stock symbols."""
        import json
        import requests
        import time
        from config import OLLAMA_BASE_URL, OLLAMA_MODEL, OLLAMA_TIMEOUT, OLLAMA_API_KEY

        logging.info(f"Ollama ({OLLAMA_MODEL}) analyzing {len(watchlist)} stocks...")

        # Prepare top-100 news headlines
        news_summary = []
        for i, item in enumerate(news_data[:100]):
            news_summary.append(f"[{i}] {item.get('headline','')} | {item.get('summary','')}")
        news_text = "\n".join(news_summary)

        system_prompt = (
            "You are a professional financial analyst. Analyze the provided news articles and "
            "determine the sentiment for each stock symbol in the watchlist.\n\n"
            "For each symbol output:\n"
            "  sentiment_score: integer 0-100 (50=neutral, 100=very bullish, 0=very bearish)\n"
            "  catalyst_strength: 'STRONG', 'MODERATE', 'WEAK', or 'NONE'\n"
            "  relevant_headlines: list of relevant headline strings\n\n"
            "Return ONLY a valid JSON object. No markdown, no extra text.\n"
            "Example: {\"RELIANCE.NS\": {\"sentiment_score\": 72, "
            "\"catalyst_strength\": \"MODERATE\", \"relevant_headlines\": [\"Reliance Q4 profit up 18%\"]}}"
        )
        user_content = f"Watchlist (analyze these only):\n{json.dumps(watchlist)}\n\nNews:\n{news_text}"

        retries = 0
        while True:
            try:
                base = OLLAMA_BASE_URL.rstrip('/')
                if base.endswith('/v1'):
                    url = f"{base}/chat/completions"
                elif base.endswith('/v1/chat/completions'):
                    url = base
                else:
                    url = f"{base}/v1/chat/completions"
                payload = {
                    "model": OLLAMA_MODEL,
                    "messages": [
                        {"role": "system", "content": system_prompt},
                        {"role": "user",   "content": user_content},
                    ],
                    "temperature": 0.0,
                    "response_format": {"type": "json_object"},
                }
                headers = {"Content-Type": "application/json"}
                if OLLAMA_API_KEY:
                    headers["Authorization"] = f"Bearer {OLLAMA_API_KEY}"
                resp = requests.post(url, headers=headers, json=payload, timeout=OLLAMA_TIMEOUT)
                resp.raise_for_status()

                body = resp.json()
                if 'choices' not in body:
                    raise RuntimeError(f"Unexpected Ollama response: {body}")

                text = body['choices'][0]['message']['content'].strip()
                # Strip markdown fences if present
                if text.startswith("```"):
                    lines = text.splitlines()
                    text = "\n".join(lines[1:-1] if lines[-1].strip() == "```" else lines[1:]).strip()

                parsed = json.loads(text)

                results = {}
                for symbol in watchlist:
                    entry = parsed.get(symbol, {})
                    score = int(entry.get("sentiment_score", 50))
                    results[symbol] = {
                        "sentiment_score":    score,
                        "sentiment":          "POSITIVE" if score > 60 else ("NEGATIVE" if score < 40 else "NEUTRAL"),
                        "relevant_headlines": entry.get("relevant_headlines", []),
                        "catalyst_strength":  entry.get("catalyst_strength", "NONE"),
                    }
                logging.info(f"Ollama AI sentiment done for {len(results)} stocks.")
                return results

            except Exception as exc:
                retries += 1
                logging.error("=" * 80)
                logging.error(f"OLLAMA AI ERROR (Attempt {retries}): {exc}")
                logging.info("Ollama is taking time to respond. Retrying in 15 seconds (stuck to Ollama mode active)...")
                logging.error("=" * 80)
                time.sleep(15)

    def _analyze_with_bedrock(self, news_data: list) -> dict:
        import json
        import requests
        from config import AWS_ACCESS_KEY_ID, AWS_SECRET_ACCESS_KEY, AWS_REGION, AWS_BEDROCK_MODEL, AWS_BEDROCK_API_KEY, NSE_WATCHLIST
        
        logging.info(f"Using AWS Bedrock ({AWS_BEDROCK_MODEL}) for AI sentiment analysis...")
        
        # Prepare news list text to keep context window clean
        news_summary = []
        for i, item in enumerate(news_data[:100]): # Limit to top 100 articles
            news_summary.append(f"[{i}] Headline: {item.get('headline')} | Summary: {item.get('summary')}")
        news_text = "\n".join(news_summary)
        
        # Construct prompt
        system_prompt = (
            "You are a professional financial analyst. Analyze the provided news articles and "
            "determine the news sentiment for the stock symbols in the watchlist.\n\n"
            "For each stock symbol, you must output:\n"
            "1. sentiment_score: An integer from 0 to 100, where 50 is neutral, 100 is extremely positive/bullish, and 0 is extremely negative/bearish.\n"
            "2. catalyst_strength: Either 'STRONG', 'MODERATE', 'WEAK', or 'NONE'.\n"
            "3. relevant_headlines: A list of headlines from the news that are related to this stock.\n\n"
            "Return the output STRICTLY as a valid JSON object. Do not include any markdown styling, conversational text, or wrapper. "
            "The JSON key must be the exact symbol from the watchlist (e.g. 'RELIANCE.NS').\n"
            "Format example:\n"
            "{\n"
            "  \"RELIANCE.NS\": {\n"
            "    \"sentiment_score\": 85,\n"
            "    \"catalyst_strength\": \"STRONG\",\n"
            "    \"relevant_headlines\": [\"Headline 1\"]\n"
            "  }\n"
            "}"
        )
        
        user_content = f"Watchlist:\n{json.dumps(NSE_WATCHLIST)}\n\nNews Articles:\n{news_text}"
        
        try:
            completion_text = ""
            if AWS_BEDROCK_API_KEY:
                # Use Bedrock API Key bearer token authentication (direct REST call)
                url = f"https://bedrock-runtime.{AWS_REGION}.amazonaws.com/model/{AWS_BEDROCK_MODEL}/invoke"
                headers = {
                    "Authorization": f"Bearer {AWS_BEDROCK_API_KEY}",
                    "Content-Type": "application/json"
                }
                payload = {
                    "anthropic_version": "bedrock-2023-05-31",
                    "max_tokens": 4096,
                    "system": system_prompt,
                    "messages": [
                        {
                            "role": "user",
                            "content": [
                                {
                                    "type": "text",
                                    "text": user_content
                                }
                            ]
                        }
                    ]
                }
                resp = requests.post(url, headers=headers, json=payload, timeout=30)
                resp.raise_for_status()
                response_body = resp.json()
                completion_text = response_body.get('content')[0].get('text').strip()
            else:
                # Use standard boto3 client signature v4 credentials
                import boto3
                session = boto3.Session(
                    aws_access_key_id=AWS_ACCESS_KEY_ID,
                    aws_secret_access_key=AWS_SECRET_ACCESS_KEY,
                    region_name=AWS_REGION
                )
                client = session.client('bedrock-runtime')
                body = json.dumps({
                    "anthropic_version": "bedrock-2023-05-31",
                    "max_tokens": 4096,
                    "system": system_prompt,
                    "messages": [
                        {
                            "role": "user",
                            "content": [
                                {
                                    "type": "text",
                                    "text": user_content
                                }
                            ]
                        }
                    ]
                })
                response = client.invoke_model(
                    modelId=AWS_BEDROCK_MODEL,
                    body=body
                )
                response_body = json.loads(response.get('body').read())
                completion_text = response_body.get('content')[0].get('text').strip()
            
            # Clean up potential markdown formatting (like ```json ... ```)
            if completion_text.startswith("```"):
                lines = completion_text.splitlines()
                if lines[0].startswith("```"):
                    lines = lines[1:]
                if lines[-1].strip() == "```":
                    lines = lines[:-1]
                completion_text = "\n".join(lines).strip()
                
            parsed_results = json.loads(completion_text)
            
            # Ensure every watchlist symbol has a default entry in the result
            results = {}
            for symbol in NSE_WATCHLIST:
                if symbol in parsed_results:
                    results[symbol] = {
                        "sentiment_score": int(parsed_results[symbol].get("sentiment_score", 50)),
                        "sentiment": "POSITIVE" if parsed_results[symbol].get("sentiment_score", 50) > 60 else ("NEGATIVE" if parsed_results[symbol].get("sentiment_score", 50) < 40 else "NEUTRAL"),
                        "relevant_headlines": parsed_results[symbol].get("relevant_headlines", []),
                        "catalyst_strength": parsed_results[symbol].get("catalyst_strength", "NONE")
                    }
                else:
                    results[symbol] = {
                        "sentiment_score": 50,
                        "sentiment": "NEUTRAL",
                        "relevant_headlines": [],
                        "catalyst_strength": "NONE"
                    }
            logging.info("Successfully completed AI sentiment analysis via Bedrock!")
            return results
            
        except Exception as e:
            logging.error(f"Failed to use AWS Bedrock for news analysis: {e}. Falling back to keyword search.")
            return {}



    async def fetch_and_score(self, watchlist, stock_symbol_map):
        """Fetch news from all sources, compute sentiment per stock.
        Returns dict: {symbol: sentiment_result}
        """
        # Gather raw news
        money = await self.scraper.scrape_moneycontrol_news()
        et = await self.scraper.scrape_et_markets_news()
        bse = await self.scraper.scrape_bse_announcements()
        nse = await self.scraper.scrape_nse_announcements()
        all_news = money + et + bse + nse
        # Score per stock
        results = {}
        for symbol in watchlist:
            # map watchlist symbol to plain name without .NS
            plain = symbol.replace('.NS', '')
            results[symbol] = self.scraper.score_news_sentiment(all_news, plain)
        # Sector summary
        sector_summary = self.scraper.get_sector_news_summary(self.sectors, all_news)
        return results, sector_summary
