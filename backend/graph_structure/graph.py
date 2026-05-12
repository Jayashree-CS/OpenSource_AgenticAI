from langgraph.graph import StateGraph
from typing import TypedDict

from agents.router_agent import route_query
from agents.hr_agent import hr_agent
from agents.it_agent import it_agent


# Define state
class GraphState(TypedDict):
    message: str
    agent: str
    response: str
    db: object
    user: object
    history: list
    session_state: object


# Router node
def router_node(state: GraphState):
    agent = route_query(state["message"])
    # Ensure the graph never crashes on unexpected route values.
    if agent not in {"hr", "it", "general"}:
        agent = "general"
    return {"agent": agent}


# HR node
def hr_node(state: GraphState):
    response = hr_agent(
        state["message"],
        state["db"],
        state["user"],
        state.get("history", []),
        session_state=state.get("session_state"),
    )
    return {"response": response, "agent": "hr"}


# IT node
def it_node(state: GraphState):
    response = it_agent(
        state["message"],
        state["db"],
        state["user"],
        state.get("history", []),
        session_state=state.get("session_state"),
    )
    return {"response": response, "agent": "it"}


# Build graph
def build_graph():
    builder = StateGraph(GraphState)

    builder.add_node("router", router_node)
    builder.add_node("hr", hr_node)
    builder.add_node("it", it_node)

    # Entry
    builder.set_entry_point("router")

    # Conditional routing
    def route(state: GraphState):
        agent = state.get("agent")
        if agent in {"hr", "it"}:
            return agent
        return "general"

    builder.add_conditional_edges(
        "router",
        route,
        {
            "hr": "hr",
            "it": "it",
            "general": "__end__",
        },
    )

    builder.add_edge("hr", "__end__")
    builder.add_edge("it", "__end__")

    return builder.compile()
