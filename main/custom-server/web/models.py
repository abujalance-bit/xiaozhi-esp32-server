import uuid
from datetime import datetime
from flask_sqlalchemy import SQLAlchemy
from flask_login import UserMixin
from werkzeug.security import generate_password_hash, check_password_hash

db = SQLAlchemy()


def new_id():
    return str(uuid.uuid4())


class User(db.Model, UserMixin):
    __tablename__ = "users"
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(50), unique=True, nullable=False)
    password_hash = db.Column(db.String(256), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)


class Agent(db.Model):
    __tablename__ = "agents"
    id = db.Column(db.String(36), primary_key=True, default=new_id)
    name = db.Column(db.String(100), nullable=False)
    system_prompt = db.Column(db.Text, default="")
    summary_memory = db.Column(db.Text, default="")
    chat_history_conf = db.Column(db.Integer, default=0)
    vad_model_id = db.Column(db.String(50), default="SileroVAD")
    asr_model_id = db.Column(db.String(50), default="FunASR")
    llm_model_id = db.Column(db.String(50), default="OllamaLLM")
    vllm_model_id = db.Column(db.String(50), default="OllamaVLLM")
    tts_model_id = db.Column(db.String(50), default="PiperTTS")
    mem_model_id = db.Column(db.String(50), default="nomem")
    intent_model_id = db.Column(db.String(50), default="function_call")
    tts_voice = db.Column(db.String(200), default="")
    tts_language = db.Column(db.String(50), default="English")
    tts_volume = db.Column(db.Integer, default=100)
    tts_rate = db.Column(db.Integer, default=100)
    tts_pitch = db.Column(db.Integer, default=100)
    is_default = db.Column(db.Boolean, default=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    devices = db.relationship("Device", backref="agent", lazy=True)


class Device(db.Model):
    __tablename__ = "devices"
    id = db.Column(db.String(36), primary_key=True, default=new_id)
    mac_address = db.Column(db.String(17), unique=True, nullable=False)
    name = db.Column(db.String(100), default="")
    agent_id = db.Column(db.String(36), db.ForeignKey("agents.id"), nullable=True)
    status = db.Column(db.String(20), default="offline")
    last_seen = db.Column(db.DateTime, nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)


class ModelConfig(db.Model):
    __tablename__ = "model_configs"
    id = db.Column(db.String(50), primary_key=True)
    type = db.Column(db.String(20), nullable=False)  # VAD, ASR, LLM, VLLM, TTS, Memory, Intent
    name = db.Column(db.String(100), nullable=False)
    description = db.Column(db.Text, default="")
    is_local = db.Column(db.Boolean, default=False)
    config_json = db.Column(db.JSON, nullable=False, default=dict)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)


class Plugin(db.Model):
    __tablename__ = "plugins"
    code = db.Column(db.String(50), primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    description = db.Column(db.Text, default="")
    enabled = db.Column(db.Boolean, default=False)
    params_json = db.Column(db.JSON, nullable=False, default=dict)


class SysParam(db.Model):
    __tablename__ = "sys_params"
    key = db.Column(db.String(100), primary_key=True)
    value = db.Column(db.Text, default="")
    value_type = db.Column(db.String(20), default="string")  # string, number, boolean, array, json
    description = db.Column(db.Text, default="")


class ChatHistory(db.Model):
    __tablename__ = "chat_history"
    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    session_id = db.Column(db.String(36), index=True)
    mac_address = db.Column(db.String(17), index=True)
    chat_type = db.Column(db.Integer)  # 1=user, 2=assistant
    content = db.Column(db.Text)
    report_time = db.Column(db.String(50))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
