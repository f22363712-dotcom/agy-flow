from agy_flow_classify import classify_task, plan_task, DEFAULT_AGENT_REGISTRY
from agy_flow.config import get_agent_registry, CONFIG_FILE
import json

def plan_task_command(args):
    """Prints a structured routing plan without creating or starting a task."""
    if CONFIG_FILE.exists():
        plan = plan_task(args.title, agent_registry=get_agent_registry())
    else:
        plan = plan_task(args.title)
    print(json.dumps(plan, indent=4, ensure_ascii=False))
