import os
from pydantic import BaseModel

class Settings(BaseModel):
    PROJECT_NAME: str = "高校发展检验报告生成系统"
    VERSION: str = "2.0.0"
    
    # 基础路径
    BASE_DIR: str = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    DATA_DIR: str = os.path.join(BASE_DIR, "data")
    UPLOAD_DIR: str = os.path.join(DATA_DIR, "uploads")
    CHARTS_DIR: str = os.path.join(BASE_DIR, "static", "charts")
    EXPORTS_DIR: str = os.path.join(DATA_DIR, "exports")
    SQLITE_PATH: str = os.path.join(DATA_DIR, "cell_lake.db")
    DUCKDB_PATH: str = os.path.join(DATA_DIR, "metrics.duckdb")
    
    # DeepSeek 模型服务配置
    DEEPSEEK_API_KEY: str = os.getenv("DEEPSEEK_API_KEY", "")
    DEEPSEEK_BASE_URL: str = os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com")
    DEEPSEEK_MODEL: str = os.getenv("DEEPSEEK_MODEL", "deepseek-chat")
    
    # Jev / Judge 评估模型
    JUDGE_MODEL: str = os.getenv("JUDGE_MODEL", "deepseek-chat")

settings = Settings()

# 确保所有目录存在
for d in [settings.DATA_DIR, settings.UPLOAD_DIR, settings.CHARTS_DIR, settings.EXPORTS_DIR]:
    os.makedirs(d, exist_ok=True)
