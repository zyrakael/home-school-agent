"""LangGraph skeleton.

Planned graph:
start -> intent_router -> slot_extractor -> readonly_tool_planner
      -> readonly_tool_executor -> analysis_builder -> knowledge_retrieve
      -> prompt_builder -> llm_generate -> guardrail_check
      -> response_assembler -> end

No graph nodes are implemented yet.
"""
