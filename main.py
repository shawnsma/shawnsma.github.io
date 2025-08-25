import os
from uuid import uuid4
from typing import Any, Dict
from fastapi import FastAPI, HTTPException, Body
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from pydantic import BaseModel
import httpx
from pathlib import Path
from dotenv import load_dotenv
load_dotenv(dotenv_path=Path(__file__).with_name(".env"))

API_KEY = os.getenv("STIGG_SERVER_API_KEY") #auth
FREE_PLAN_ID = os.getenv("STIGG_FREE_PLAN_ID") #default free

if not API_KEY:
    raise RuntimeError("Missing STIGG_SERVER_API_KEY in .env")
if not FREE_PLAN_ID:
    raise RuntimeError("Missing STIGG_FREE_PLAN_ID in .env")

FEATURE_BOOL = os.getenv("FEATURE_BOOL", "brewery_map_enabled")
FEATURE_CONFIG = os.getenv("FEATURE_CONFIG", "brewery_max_results_v2")
FEATURE_METERED_RAW = os.getenv("FEATURE_METERED_RAW", "brewery_marker_clicks")
FEATURE_METERED_USAGE = os.getenv("FEATURE_METERED_USAGE", "brewery_map_loads")
RAW_EVENT_NAME = os.getenv("RAW_EVENT_NAME", "brewery_marker_click") # link to click meter
RAW_EVENT_MAP_LOAD = "brewery_map_load"

STIGG_URL = "https://api.stigg.io/graphql"
HEADERS = {"X-API-KEY": API_KEY, "Content-Type": "application/json"} # header format

app = FastAPI()
app.add_middleware(
    CORSMiddleware, # def
    allow_origins=["*"], # any domain
    allow_credentials=True, # cookies, auth readers, etc.
    allow_methods=["*"], # HTTP methods
    allow_headers=["*"], # custom headers
) # change in prod

# pydantic models, santize inputs
class CustomerBody(BaseModel):
    customerId: str
    email: str | None = None
    planId: str | None = None

class SubscribeBody(BaseModel):
    customerId: str
    planId: str | None = None

class MarkerClickBody(BaseModel):
    customerId: str

class MapLoadBody(BaseModel):
    customerId: str

# wrapper for all following HTTP requests
async def gql(query: str, variables: Dict[str, Any]) -> Dict[str, Any]:
    async with httpx.AsyncClient(timeout=20) as client:
        r = await client.post(STIGG_URL, headers=HEADERS, json={"query": query, "variables": variables})
        try:
            payload = r.json()
        except Exception:
            payload = {"raw": r.text}

        if r.status_code != 200:
            raise HTTPException(500, f"Stigg HTTP {r.status_code}: {payload}") # clarify HTTP errors
        if isinstance(payload, dict) and "errors" in payload:
            raise HTTPException(500, f"Stigg GraphQL error: {payload['errors']}") # clarify GraphQL errors

        return payload.get("data", {})

# Health check
@app.get("/api/stigg/health")
def health():
    return {"ok": True}

@app.get("/")
def root():
    return FileResponse(Path(__file__).with_name("index.html"))

# -------- Routes --------
@app.post("/api/stigg/customer")
async def provision_customer(body: CustomerBody):
    # 1) CREATE via provisionCustomer
    q = """
    mutation ProvisionCustomer($input: ProvisionCustomerInput!) {
      provisionCustomer(input: $input) {
        customer { id refId email name }
        subscriptionDecisionStrategy
        subscription { refId status plan { refId } }
      }
    }
    """
    inp = {
        "customerId": body.customerId,
        "email": body.email,
        "subscriptionParams": {
            "planId": body.planId or FREE_PLAN_ID,
            "billingPeriod": "MONTHLY"
        }
    }

    try:
        data = await gql(q, {"input": inp})
        return data["provisionCustomer"]

    except HTTPException as e:
        # 2) if duplicate, FETCH by refId (external id)
        detail = str(e.detail)
        if "Duplicat" in detail:
            get_q = """
            query GetCustomerByRefId($input: GetCustomerByRefIdInput!) {
              getCustomerByRefId(input: $input) {
                id
                refId
                email
                name
              }
            }
            """
            got = await gql(get_q, {"input": {"customerId": body.customerId}})
            c = got.get("getCustomerByRefId")
            if not c:
                raise
            return {"customer": c, "subscription": None}
        raise


@app.post("/api/stigg/subscribe")
async def subscribe(payload: dict = Body(...)):
    customer_ref = payload.get("customerRefId") or payload.get("customerId")
    plan_ref = payload.get("planRefId") or payload.get("planId")
    if not customer_ref or not plan_ref:
        raise HTTPException(status_code=400, detail="customerRefId and planRefId are required")

    q = """
    mutation CreateSubscription($input: ProvisionSubscriptionInput!) {  
    provisionSubscription: provisionSubscriptionV2(input: $input) {  
        id
        status
    }
    }
    """
    variables = {
        "input": {
            "customerId": customer_ref,
            "planId": plan_ref,
            "billingPeriod": "MONTHLY"
        }
    }

    data = await gql(q, {"input": variables["input"]})
    sub = data.get("provisionSubscription")
    if not sub:
        raise HTTPException(500, f"Unexpected response: {data}")
    return {"ok": True, "subscription": sub}


@app.get("/api/stigg/entitlements")
async def get_entitlements(customerId: str):
    q = """
    query GetEntitlements($query: FetchEntitlementsQuery!) {
    cachedEntitlements(query: $query) {
        feature { refId displayName featureType meterType description }
        currentUsage
        usageLimit
        hasUnlimitedUsage
        usagePeriodAnchor
        usagePeriodStart
        usagePeriodEnd
        resetPeriod
    }
    }
    """
    data = await gql(q, {"query": {"customerId": customerId}})
    return data

@app.post("/api/stigg/usage/marker-click")
async def report_marker_click(body: MarkerClickBody):
    q = """
    mutation ReportEvent($events: UsageEventsReportInput!) {
    reportEvent(events: $events)
    }
    """
    vars = {
        "events": {
            "usageEvents": [
                {
                    "customerId": body.customerId,
                    "eventName": RAW_EVENT_NAME,
                    "idempotencyKey": str(uuid4()),
                }
            ]
        }
    }
    data = await gql(q, vars)
    return {"ok": True, "result": data["reportEvent"]}

@app.post("/api/stigg/usage/map-load")
async def report_map_load(payload: dict = Body(...)):
    customer_id = payload.get("customerId")
    if not customer_id:
        raise HTTPException(400, "customerId required")

    query = """
    mutation ReportUsage($input: ReportUsageInput!) {
      reportUsage(input: $input) { id }
    }
    """
    variables = {
        "input": {
            "customerId": customer_id,
            "featureId": FEATURE_METERED_USAGE,
            "value": 1
        }
    }
    data = await gql(query, variables)
    return {"ok": True, "id": data.get("reportUsage", {}).get("id")}