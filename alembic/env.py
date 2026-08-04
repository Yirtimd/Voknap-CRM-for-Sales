from logging.config import fileConfig

from alembic import context
from sqlalchemy import engine_from_config, pool

from app.core.config import settings
from app.core.database import Base
from app.modules.accounts import models as accounts_models  # noqa: F401
from app.modules.activity import models as activity_models  # noqa: F401
from app.modules.ai_agent import models as ai_agent_models  # noqa: F401
from app.modules.automation import models as automation_models  # noqa: F401
from app.modules.communication import models as communication_models  # noqa: F401
from app.modules.connectors import models as connectors_models  # noqa: F401
from app.modules.custom_fields import models as custom_field_models  # noqa: F401
from app.modules.knowledge import models as knowledge_models  # noqa: F401
from app.modules.notifications import models as notification_models  # noqa: F401
from app.modules.production import models as production_models  # noqa: F401
from app.modules.sales import models as sales_models  # noqa: F401
from app.modules.sequences import models as sequence_models  # noqa: F401
from app.modules.templates import models as templates_models  # noqa: F401


config = context.config
config.set_main_option("sqlalchemy.url", settings.database_url)

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata


def run_migrations_offline() -> None:
    context.configure(
        url=settings.database_url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    configuration = config.get_section(config.config_ini_section, {})
    configuration["sqlalchemy.url"] = settings.database_url
    connectable = engine_from_config(
        configuration,
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    with connectable.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata)

        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
