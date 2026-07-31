from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.modules.activity import models as activity_models  # noqa: F401
from app.modules.ai_agent import models as ai_agent_models  # noqa: F401
from app.modules.automation import models as automation_models  # noqa: F401
from app.modules.communication import models as communication_models  # noqa: F401
from app.modules.connectors import models as connectors_models  # noqa: F401
from app.modules.knowledge import models as knowledge_models  # noqa: F401
from app.modules.notifications import models as notification_models  # noqa: F401
from app.modules.production import models as production_models  # noqa: F401
from app.modules.sales import models as sales_models  # noqa: F401
from app.modules.sequences import models as sequence_models  # noqa: F401
from app.modules.templates import models as templates_models  # noqa: F401
from app.modules.activity.router import router as activity_router
from app.modules.accounts.router import router as accounts_router
from app.modules.accounts.team_router import router as team_router
from app.modules.ai_agent.router import router as ai_agent_router
from app.modules.analytics.router import router as analytics_router
from app.modules.automation.router import router as automation_router
from app.modules.auth.router import router as auth_router
from app.modules.communication.router import router as communication_router
from app.modules.connectors.router import router as connectors_router
from app.modules.connectors.public_router import router as public_api_router
from app.modules.health.router import router as health_router
from app.modules.knowledge.router import router as knowledge_router
from app.modules.notifications.router import router as notifications_router
from app.modules.me.router import router as me_router
from app.modules.production.router import router as production_router
from app.modules.sales.router import router as sales_router
from app.modules.sales.lifecycle_router import router as sales_lifecycle_router
from app.modules.sales.scoring_router import router as sales_scoring_router
from app.modules.sequences.router import router as sequences_router
from app.modules.templates.router import router as templates_router


app = FastAPI(title="CRM Sales App", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/")
def root() -> dict[str, str]:
    return {
        "app": "CRM Sales App",
        "status": "running",
        "docs": "/docs",
        "health": "/health",
    }


app.include_router(health_router, tags=["health"])
app.include_router(auth_router, prefix="/auth", tags=["auth"])
app.include_router(accounts_router, prefix="/accounts", tags=["accounts"])
app.include_router(team_router, prefix="/accounts", tags=["team-management"])
app.include_router(me_router, tags=["me"])
app.include_router(activity_router, prefix="/activities", tags=["activities"])
app.include_router(sales_router, prefix="/sales", tags=["sales"])
app.include_router(sales_lifecycle_router, prefix="/sales", tags=["sales-lifecycle"])
app.include_router(sales_scoring_router, prefix="/sales", tags=["sales-scoring"])
app.include_router(sequences_router, prefix="/sequences", tags=["sequences"])
app.include_router(knowledge_router, prefix="/knowledge", tags=["knowledge"])
app.include_router(notifications_router, prefix="/notifications", tags=["notifications"])
app.include_router(ai_agent_router, prefix="/ai-agent", tags=["ai-agent"])
app.include_router(analytics_router, prefix="/analytics", tags=["analytics"])
app.include_router(automation_router, prefix="/automations", tags=["automations"])
app.include_router(communication_router, prefix="/communication", tags=["communication"])
app.include_router(connectors_router, prefix="/connectors", tags=["connectors"])
app.include_router(public_api_router, prefix="/public/v1", tags=["public-api"])
app.include_router(templates_router, prefix="/templates", tags=["templates"])
app.include_router(production_router, prefix="/production", tags=["production"])
