#!/usr/bin/env python3
"""
🚀 COMPLETE AML PIPELINE DEMONSTRATION - AZURE SERVICE BUS VERSION
Uses the deployed Azure Container Apps gateway + JWT authentication.
Configuration is read from environment variables.
"""

import requests
import json
import time
import asyncio
import os
from datetime import datetime
from typing import Dict, Any, List

# ========== CONFIGURATION FROM ENVIRONMENT ==========
GATEWAY_URL = os.getenv("AML_GATEWAY_URL", "http://20.87.96.47:8000")
JWT_TOKEN = os.getenv("AML_JWT_TOKEN", "add_your_valid_jwt_token")
# ===================================================

HEADERS = {
    "Authorization": f"Bearer {JWT_TOKEN}",
    "accept": "application/json",
    "Content-Type": "application/json"
}

def print_header(title: str, level: int = 1):
    if level == 1:
        print("\n" + "="*80)
        print(f"🚀 {title}")
        print("="*80)
    elif level == 2:
        print(f"\n📋 {title}")
        print("-" * 60)
    else:
        print(f"\n🔸 {title}")

def print_json(data: Any, title: str = "Data", max_items: int = 3):
    print(f"\n📊 {title}:")
    if isinstance(data, list) and len(data) > max_items:
        print(json.dumps(data[:max_items], indent=2, default=str))
        print(f"... and {len(data) - max_items} more items")
    else:
        print(json.dumps(data, indent=2, default=str))

def check_services() -> bool:
    """Check if gateway is reachable (other services are internal)"""
    print_header("Service Health Check (via Gateway)", 2)
    try:
        resp = requests.get(f"{GATEWAY_URL}/health", headers=HEADERS, timeout=10)
        if resp.status_code == 200:
            print(f"   ✅ Gateway is healthy")
            return True
        else:
            print(f"   ❌ Gateway returned {resp.status_code}")
            return False
    except Exception as e:
        print(f"   ❌ Cannot reach gateway: {e}")
        return False

def load_fixture_data() -> Dict[str, List[Dict]]:
    """Load test data from fixtures directory (same as original)"""
    print_header("Loading Test Data from Fixtures", 2)
    try:
        with open("fixtures/accounts.json", "r") as f:
            accounts = json.load(f)
        with open("fixtures/customers.json", "r") as f:
            customers = json.load(f)
        with open("fixtures/transactions.json", "r") as f:
            transactions = json.load(f)
        data = {"accounts": accounts, "customers": customers, "transactions": transactions}
        print(f"✅ Loaded: {len(accounts)} accounts, {len(customers)} customers, {len(transactions)} transactions")
        return data
    except Exception as e:
        print(f"❌ Error loading fixtures: {e}")
        return {}

def stage_1_ingestion(data: Dict[str, List[Dict]]) -> bool:
    """Upload fixture data through gateway (assumes /v1/batch endpoint)"""
    print_header("STAGE 1: Data Ingestion via Azure Gateway", 1)
    try:
        # Save to temp files
        with open("temp_accounts.json", "w") as f:
            json.dump(data["accounts"], f)
        with open("temp_customers.json", "w") as f:
            json.dump(data["customers"], f)
        with open("temp_transactions.json", "w") as f:
            json.dump(data["transactions"], f)

        files = {
            'accounts': ('accounts.json', open('temp_accounts.json', 'rb'), 'application/json'),
            'customers': ('customers.json', open('temp_customers.json', 'rb'), 'application/json'),
            'transactions': ('transactions.json', open('temp_transactions.json', 'rb'), 'application/json')
        }
        batch_url = f"{GATEWAY_URL}/v1/batch"
        print(f"📤 Uploading to {batch_url}")
        response = requests.post(batch_url, files=files, headers={"Authorization": HEADERS["Authorization"]}, timeout=230)
        for f in files.values():
            f[1].close()
        if response.status_code in [200, 201]:
            print("✅ Ingestion successful!")
            print_json(response.json(), "Ingestion Response")
            return True
        else:
            print(f"❌ Ingestion failed: {response.status_code} - {response.text}")
            return False
    except Exception as e:
        print(f"❌ Ingestion error: {e}")
        return False

def stage_2_feature_engineering() -> Dict:
    """Get features via gateway (assumes /v1/features)"""
    print_header("STAGE 2: Feature Engineering", 1)
    time.sleep(8)
    try:
        resp = requests.get(f"{GATEWAY_URL}/v1/features", headers=HEADERS, timeout=10)
        if resp.status_code == 200:
            data = resp.json()
            features = data.get("features", [])
            print(f"✅ Retrieved {len(features)} feature sets")
            return data
        else:
            print(f"❌ Failed: {resp.status_code}")
            return {}
    except Exception as e:
        print(f"❌ Error: {e}")
        return {}

def stage_3_risk_scoring() -> Dict:
    """Get risk scores via gateway (assumes /v1/scores)"""
    print_header("STAGE 3: Risk Scoring", 1)
    time.sleep(5)
    try:
        resp = requests.get(f"{GATEWAY_URL}/v1/scores", headers=HEADERS, timeout=10)
        if resp.status_code == 200:
            data = resp.json()
            scores = data.get("scores", [])
            print(f"✅ Retrieved {len(scores)} risk scores")
            if scores:
                latest = scores[-1]
                print(f"   Latest score: {latest.get('risk_score',0):.3f} for {latest.get('txn_id','')}")
            return data
        else:
            print(f"❌ Failed: {resp.status_code}")
            return {}
    except Exception as e:
        print(f"❌ Error: {e}")
        return {}

def stage_4_alert_generation() -> Dict:
    """Get alerts via gateway (your dashboard uses /v1/alerts)"""
    print_header("STAGE 4: Alert Generation", 1)
    time.sleep(5)
    try:
        resp = requests.get(f"{GATEWAY_URL}/v1/alerts", headers=HEADERS, timeout=10)
        if resp.status_code == 200:
            data = resp.json()
            alerts = data.get("alerts", data) if isinstance(data, dict) else data
            print(f"✅ Retrieved {len(alerts)} alerts")
            return {"alerts": alerts}
        else:
            print(f"❌ Failed: {resp.status_code}")
            return {}
    except Exception as e:
        print(f"❌ Error: {e}")
        return {}

async def stage_5_ai_sar_demonstration() -> List[Dict]:
    """Show SAR narratives from alerts"""
    print_header("STAGE 5: AI-Powered SAR Generation", 1)
    try:
        resp = requests.get(f"{GATEWAY_URL}/v1/alerts", headers=HEADERS, timeout=10)
        if resp.status_code == 200:
            data = resp.json()
            alerts = data.get("alerts", data) if isinstance(data, dict) else data
            sars = [a for a in alerts if a.get('sar_narrative')]
            for i, sar in enumerate(sars, 1):
                print(f"\n🔸 SAR #{i} for {sar.get('txn_id')}")
                print(f"{'='*60}\n{sar['sar_narrative'][:1000]}\n{'='*60}")
            return sars
        else:
            print(f"❌ Failed to fetch alerts")
            return []
    except Exception as e:
        print(f"❌ Error: {e}")
        return []

def stage_6_final_analysis(generated_sars):
    print_header("STAGE 6: Complete Pipeline Analysis", 1)
    print("🎯 Pipeline Summary (Azure Service Bus deployment):")
    print(f"   ✅ Data ingestion via gateway batch endpoint")
    print(f"   ✅ Features and risk scores retrieved")
    print(f"   ✅ {len(generated_sars)} SAR narratives generated")
    print("   ✅ All data now available in your Streamlit dashboard")

async def run_complete_demonstration():
    print_header("🚀 COMPLETE AML PIPELINE ON AZURE (SERVICE BUS)", 1)
    print(f"🌐 Using Gateway: {GATEWAY_URL}")
    if not check_services():
        print("❌ Gateway not reachable. Check URL and token.")
        return
    data = load_fixture_data()
    if not data:
        return
    if not stage_1_ingestion(data):
        print("❌ Ingestion failed")
        return
    stage_2_feature_engineering()
    stage_3_risk_scoring()
    stage_4_alert_generation()
    sars = await stage_5_ai_sar_demonstration()
    stage_6_final_analysis(sars)
    print_header("🎉 DEMO FINISHED", 1)

if __name__ == "__main__":
    asyncio.run(run_complete_demonstration())
