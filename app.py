from fastapi import FastAPI, HTTPException, Depends, File, UploadFile, Form, status
from fastapi.security import OAuth2PasswordBearer
from fastapi.responses import HTMLResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from supabase import create_client, Client
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from datetime import datetime, timedelta
import os
import jwt
import bcrypt
from typing import Optional, List
import io

app = FastAPI()


# CORS for front-end development
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Adjust for production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Supabase setup
def init_supabase():
    try:
        url = os.getenv("SUPABASE_URL")
        key = os.getenv("SUPABASE_KEY")
        if not url or not key:
            raise ValueError("Supabase URL or Key not provided")
        if not url.startswith("https://"):
            url = f"https://{url}"
        return create_client(url, key)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to connect to Supabase: {str(e)}")

supabase = init_supabase()

# JWT setup
SECRET_KEY = os.getenv("SECRET_KEY", "your-secret-key")  # Set in Render
ALGORITHM = "HS256"

# Pydantic models
class UserLogin(BaseModel):
    name: str
    password: str

class KPI(BaseModel):
    metric: str
    threshold: float

class PerformanceData(BaseModel):
    agent_name: str
    attendance: float
    quality_score: float
    product_knowledge: float
    contact_success_rate: float
    onboarding: float
    reporting: float
    talk_time: float
    resolution_rate: float
    aht: float
    csat: float
    call_volume: int
    date: Optional[str] = None

class Goal(BaseModel):
    agent_name: str
    metric: str
    target_value: float
    manager_name: str

class Feedback(BaseModel):
    agent_name: str
    message: str

class FeedbackResponse(BaseModel):
    feedback_id: int
    manager_response: str
    manager_name: str

class AudioAssessment(BaseModel):
    agent_name: str
    audio_url: str
    upload_timestamp: str
    assessment_notes: str
    uploaded_by: str

# Authentication
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="login")

async def get_current_user(token: str = Depends(oauth2_scheme)):
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        username: str = payload.get("sub")
        role: str = payload.get("role")
        if username is None or role is None:
            raise HTTPException(status_code=401, detail="Invalid token")
        return {"name": username, "role": role}
    except Exception:
        raise HTTPException(status_code=401, detail="Invalid token")

def authenticate_user(supabase: Client, name: str, password: str):
    try:
        user_response = supabase.table("users").select("*").eq("name", name).execute()
        if user_response.data:
            # Replace with proper password hashing in production
            return True, name, user_response.data[0]["role"]
        return False, None, None
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Authentication error: {str(e)}")

# Supabase functions (reused from original)
def check_db(supabase: Client):
    required_tables = ["users", "kpis", "performance", "zoho_agent_data", "goals", "feedback", "notifications", "audio_assessments"]
    critical_tables = ["users", "goals", "feedback", "performance"]
    missing_critical = []
    missing_non_critical = []
    
    for table in required_tables:
        try:
            supabase.table(table).select("count").limit(1).execute()
        except Exception as e:
            if 'relation' in str(e).lower() and 'does not exist' in str(e).lower():
                if table in critical_tables:
                    missing_critical.append(table)
                else:
                    missing_non_critical.append(table)
            else:
                raise HTTPException(status_code=500, detail=f"Error accessing {table}: {str(e)}")
    
    if missing_critical:
        raise HTTPException(status_code=500, detail=f"Critical tables missing: {', '.join(missing_critical)}")
    return {"notifications_enabled": "notifications" not in missing_non_critical}

def save_kpis(supabase: Client, kpis: dict):
    try:
        for metric, threshold in kpis.items():
            response = supabase.table("kpis").select("*").eq("metric", metric).execute()
            if not response.data:
                supabase.table("kpis").insert({"metric": metric, "threshold": threshold}).execute()
            else:
                supabase.table("kpis").update({"threshold": threshold}).eq("metric", metric).execute()
        return True
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error saving KPIs: {str(e)}")

def get_kpis(supabase: Client):
    try:
        response = supabase.table("kpis").select("*").execute()
        kpis = {}
        for row in response.data:
            metric = row["metric"]
            value = row["threshold"]
            kpis[metric] = int(float(value)) if metric == "call_volume" else float(value) if value is not None else 0.0
        return kpis
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error retrieving KPIs: {str(e)}")

def save_performance(supabase: Client, agent_name: str, data: dict):
    try:
        date = data.get('date', datetime.now().strftime("%Y-%m-%d"))
        performance_data = {
            "agent_name": agent_name,
            "attendance": data['attendance'],
            "quality_score": data['quality_score'],
            "product_knowledge": data['product_knowledge'],
            "contact_success_rate": data['contact_success_rate'],
            "onboarding": data['onboarding'],
            "reporting": data['reporting'],
            "talk_time": data['talk_time'],
            "resolution_rate": data['resolution_rate'],
            "aht": data['aht'],
            "csat": data['csat'],
            "call_volume": data['call_volume'],
            "date": date
        }
        supabase.table("performance").insert(performance_data).execute()
        update_goal_status(supabase, agent_name)
        return True
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error saving performance data: {str(e)}")

def get_performance(supabase: Client, agent_name: Optional[str] = None):
    try:
        query = supabase.table("performance").select("*")
        if agent_name:
            query = query.eq("agent_name", agent_name)
        response = query.execute()
        if response.data:
            df = pd.DataFrame(response.data)
            numeric_cols = ['attendance', 'quality_score', 'product_knowledge', 'contact_success_rate', 
                           'onboarding', 'reporting', 'talk_time', 'resolution_rate', 'aht', 'csat']
            for col in numeric_cols:
                if col in df.columns:
                    df[col] = pd.to_numeric(df[col], errors='coerce')
            if 'call_volume' in df.columns:
                df['call_volume'] = pd.to_numeric(df['call_volume'], errors='coerce').fillna(0).astype(int)
            return df.to_dict(orient="records")
        return []
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error retrieving performance data: {str(e)}")

def get_zoho_agent_data(supabase: Client, agent_name: Optional[str] = None):
    try:
        all_data = []
        chunk_size = 1000
        offset = 0
        while True:
            query = supabase.table("zoho_agent_data").select("*").range(offset, offset + chunk_size - 1)
            if agent_name:
                query = query.eq("ticket_owner", agent_name)
            response = query.execute()
            if not response.data:
                break
            all_data.extend(response.data)
            if len(response.data) < chunk_size:
                break
            offset += chunk_size
        if all_data:
            df = pd.DataFrame(all_data)
            if 'id' not in df.columns or 'ticket_owner' not in df.columns:
                raise HTTPException(status_code=400, detail="Missing required columns in zoho_agent_data")
            return df.to_dict(orient="records")
        return []
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error retrieving Zoho agent data: {str(e)}")

def set_agent_goal(supabase: Client, agent_name: str, metric: str, target_value: float, manager_name: str):
    try:
        schema_check = supabase.table("goals").select("created_by").limit(1).execute()
        include_created_by = 'created_by' in schema_check.data[0] if schema_check.data else False
        goal_data = {
            "agent_name": agent_name,
            "metric": metric,
            "target_value": target_value,
            "status": "Pending"
        }
        if include_created_by:
            goal_data["created_by"] = manager_name
        response = supabase.table("goals").select("*").eq("agent_name", agent_name).eq("metric", metric).execute()
        if response.data:
            supabase.table("goals").update(goal_data).eq("agent_name", agent_name).eq("metric", metric).execute()
        else:
            supabase.table("goals").insert(goal_data).execute()
        return True
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error setting goal: {str(e)}")

def update_goal_status(supabase: Client, agent_name: str):
    try:
        goals = supabase.table("goals").select("*").eq("agent_name", agent_name).execute()
        perf = pd.DataFrame(get_performance(supabase, agent_name))
        if not goals.data or perf.empty:
            return
        latest_perf = perf[perf['date'] == perf['date'].max()]
        for goal in goals.data:
            metric = goal['metric']
            target = goal['target_value']
            if metric in latest_perf.columns:
                value = latest_perf[metric].iloc[0]
                status = "Achieved" if (metric == "aht" and value <= target) or (metric != "aht" and value >= target) else "Pending"
                supabase.table("goals").update({"status": status}).eq("id", goal['id']).execute()
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error updating goal status: {str(e)}")

def get_feedback(supabase: Client, agent_name: Optional[str] = None):
    try:
        query = supabase.table("feedback").select("*")
        if agent_name:
            query = query.eq("agent_name", agent_name)
        response = query.execute()
        return response.data if response.data else []
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error retrieving feedback: {str(e)}")

def respond_to_feedback(supabase: Client, feedback_id: int, manager_response: str, manager_name: str):
    try:
        schema_check = supabase.table("feedback").select("updated_by").limit(1).execute()
        include_updated_by = 'updated_by' in schema_check.data[0] if schema_check.data else False
        response_data = {
            "manager_response": manager_response,
            "response_timestamp": datetime.now().isoformat()
        }
        if include_updated_by:
            response_data["updated_by"] = manager_name
        supabase.table("feedback").update(response_data).eq("id", feedback_id).execute()
        return True
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error responding to feedback: {str(e)}")

def get_notifications(supabase: Client, user_name: str, notifications_enabled: bool):
    if not notifications_enabled:
        return []
    try:
        user_response = supabase.table("users").select("id").eq("name", user_name).execute()
        if not user_response.data:
            return []
        user_id = user_response.data[0]["id"]
        response = supabase.table("notifications").select("*").eq("user_id", user_id).eq("read", False).execute()
        return response.data if response.data else []
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error retrieving notifications: {str(e)}")

def assess_performance(performance_data: List[dict], kpis: dict):
    if not performance_data:
        return []
    df = pd.DataFrame(performance_data)
    metrics = ['attendance', 'quality_score', 'product_knowledge', 'contact_success_rate', 
               'onboarding', 'reporting', 'talk_time', 'resolution_rate', 'csat', 'call_volume']
    for metric in metrics:
        if metric in df.columns:
            df[f'{metric}_pass'] = df[metric] <= kpis.get(metric, 600) if metric == 'aht' else df[metric] >= kpis.get(metric, 50)
    pass_columns = [f'{m}_pass' for m in metrics if f'{m}_pass' in df.columns]
    if pass_columns:
        df['overall_score'] = df[pass_columns].mean(axis=1) * 100
    return df.to_dict(orient="records")

def upload_audio(supabase: Client, agent_name: str, audio_file: UploadFile, manager_name: str):
    try:
        file_name = f"{agent_name}_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{audio_file.filename}"
        res = supabase.storage.from_("call-audio").upload(file_name, audio_file.file.read())
        audio_url = supabase.storage.from_("call-audio").get_public_url(file_name)
        supabase.table("audio_assessments").insert({
            "agent_name": agent_name,
            "audio_url": audio_url,
            "upload_timestamp": datetime.now().isoformat(),
            "assessment_notes": "",
            "uploaded_by": manager_name
        }).execute()
        return True
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error uploading audio: {str(e)}")

def get_audio_assessments(supabase: Client, agent_name: Optional[str] = None):
    try:
        query = supabase.table("audio_assessments").select("*")
        if agent_name:
            query = query.eq("agent_name", agent_name)
        response = query.execute()
        return response.data if response.data else []
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error retrieving audio assessments: {str(e)}")

def update_assessment_notes(supabase: Client, audio_id: int, notes: str):
    try:
        supabase.table("audio_assessments").update({"assessment_notes": notes}).eq("id", audio_id).execute()
        return True
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error updating assessment notes: {str(e)}")

# API Routes
@app.post("/login")
async def login(user: UserLogin):
    success, name, role = authenticate_user(supabase, user.name, user.password)
    if not success:
        raise HTTPException(status_code=401, detail="Invalid credentials")
    token = jwt.encode({"sub": name, "role": role}, SECRET_KEY, algorithm=ALGORITHM)
    return {"access_token": token, "token_type": "bearer", "name": name, "role": role}

@app.get("/check_db")
async def check_database(current_user: dict = Depends(get_current_user)):
    return check_db(supabase)

@app.get("/kpis")
async def get_kpis_endpoint(current_user: dict = Depends(get_current_user)):
    return get_kpis(supabase)

@app.post("/kpis")
async def save_kpis_endpoint(kpis: dict, current_user: dict = Depends(get_current_user)):
    if save_kpis(supabase, kpis):
        return {"message": "KPIs saved"}
    raise HTTPException(status_code=500, detail="Failed to save KPIs")

@app.get("/performance")
async def get_performance_endpoint(agent_name: Optional[str] = None, current_user: dict = Depends(get_current_user)):
    return get_performance(supabase, agent_name)

@app.post("/performance")
async def save_performance_endpoint(data: PerformanceData, current_user: dict = Depends(get_current_user)):
    if save_performance(supabase, data.agent_name, data.dict()):
        return {"message": "Performance saved"}
    raise HTTPException(status_code=500, detail="Failed to save performance")

@app.post("/performance/csv")
async def upload_performance_csv(file: UploadFile = File(...), current_user: dict = Depends(get_current_user)):
    try:
        df = pd.read_csv(io.BytesIO(await file.read()))
        required_cols = ['agent_name', 'attendance', 'quality_score', 'product_knowledge', 'contact_success_rate',
                        'onboarding', 'reporting', 'talk_time', 'resolution_rate', 'aht', 'csat', 'call_volume']
        if all(col in df.columns for col in required_cols):
            for _, row in df.iterrows():
                data = {col: row[col] for col in required_cols[1:]}
                if 'date' in row:
                    data['date'] = row['date']
                save_performance(supabase, row['agent_name'], data)
            return {"message": f"Imported data for {len(df)} agents"}
        raise HTTPException(status_code=400, detail="CSV missing required columns")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error processing CSV: {str(e)}")

@app.get("/zoho")
async def get_zoho_data(agent_name: Optional[str] = None, current_user: dict = Depends(get_current_user)):
    return get_zoho_agent_data(supabase, agent_name)

@app.post("/goals")
async def set_goal_endpoint(goal: Goal, current_user: dict = Depends(get_current_user)):
    if set_agent_goal(supabase, goal.agent_name, goal.metric, goal.target_value, goal.manager_name):
        return {"message": "Goal set"}
    raise HTTPException(status_code=500, detail="Failed to set goal")

@app.get("/goals")
async def get_goals(agent_names: Optional[str] = None, current_user: dict = Depends(get_current_user)):
    query = supabase.table("goals").select("*")
    if agent_names:
        query = query.in_("agent_name", agent_names.split(","))
    response = query.execute()
    return response.data if response.data else []

@app.post("/feedback")
async def submit_feedback(feedback: Feedback, current_user: dict = Depends(get_current_user)):
    try:
        supabase.table("feedback").insert({
            "agent_name": feedback.agent_name,
            "message": feedback.message
        }).execute()
        return {"message": "Feedback submitted"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error submitting feedback: {str(e)}")

@app.get("/feedback")
async def get_feedback_endpoint(agent_name: Optional[str] = None, current_user: dict = Depends(get_current_user)):
    return get_feedback(supabase, agent_name)

@app.post("/feedback/respond")
async def respond_feedback_endpoint(data: FeedbackResponse, current_user: dict = Depends(get_current_user)):
    if respond_to_feedback(supabase, data.feedback_id, data.manager_response, data.manager_name):
        return {"message": "Response sent"}
    raise HTTPException(status_code=500, detail="Failed to send response")

@app.get("/notifications")
async def get_notifications_endpoint(current_user: dict = Depends(get_current_user)):
    notifications_enabled = check_db(supabase)["notifications_enabled"]
    return get_notifications(supabase, current_user["name"], notifications_enabled)

@app.post("/audio")
async def upload_audio_endpoint(
    agent_name: str = Form(...),
    audio_file: UploadFile = File(...),
    current_user: dict = Depends(get_current_user)
):
    if upload_audio(supabase, agent_name, audio_file, current_user["name"]):
        return {"message": "Audio uploaded"}
    raise HTTPException(status_code=500, detail="Failed to upload audio")

@app.get("/audio_assessments")
async def get_audio_assessments_endpoint(agent_name: Optional[str] = None, current_user: dict = Depends(get_current_user)):
    return get_audio_assessments(supabase, agent_name)

@app.post("/audio_assessments/notes")
async def update_assessment_notes_endpoint(audio_id: int, notes: str, current_user: dict = Depends(get_current_user)):
    if update_assessment_notes(supabase, audio_id, notes):
        return {"message": "Notes saved"}
    raise HTTPException(status_code=500, detail="Failed to save notes")

@app.get("/assess_performance")
async def assess_performance_endpoint(agent_name: Optional[str] = None, current_user: dict = Depends(get_current_user)):
    performance_data = get_performance(supabase, agent_name)
    kpis = get_kpis(supabase)
    return assess_performance(performance_data, kpis)
