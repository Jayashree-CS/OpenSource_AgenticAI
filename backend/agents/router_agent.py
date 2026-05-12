import json
import re
from llm import get_llm

# Pre-defined semantic map for normalization
SEMANTIC_MAP = {
    "vpn": "VPN_SUPPORT_REQUEST",
    "wifi": "NETWORK_SUPPORT_REQUEST",
    "internet": "NETWORK_SUPPORT_REQUEST",
    "password": "CREDENTIAL_SUPPORT_REQUEST",
    "laptop": "HARDWARE_SUPPORT_REQUEST",
    "monitor": "HARDWARE_SUPPORT_REQUEST",
    "printer": "HARDWARE_SUPPORT_REQUEST",
    "leave": "HR_LEAVE_REQUEST",
    "vacation": "HR_LEAVE_REQUEST",
    "sick": "HR_LEAVE_REQUEST",
    "asset": "IT_ASSET_REQUEST",
    "ticket": "IT_TICKET_REQUEST"
}

def normalize_query(message: str) -> str:
    """Normalize user query by mapping keywords to semantic categories."""
    msg = message.lower()
    for keyword, semantic in SEMANTIC_MAP.items():
        if keyword in msg:
            return f"{semantic}: {message}"
    return message

def _clean_json(raw: str) -> str:
    raw = raw.strip()
    raw = re.sub(r"^```(?:json)?", "", raw, flags=re.IGNORECASE).strip()
    raw = re.sub(r"```$", "", raw).strip()
    match = re.search(r"\{.*\}", raw, re.DOTALL)
    if match:
        return match.group(0)
    return raw

def route_query(message: str):
    normalized_msg = normalize_query(message)
    msg_lower = normalized_msg.lower()

    # Deterministic HR routing
    if re.search(
        r"\b(confirm\s+)?(approve|reject)\s+leave\s+#?\d+\b|"
        r"\bcancel\s+leave\s+#?\d+\b|"
        r"\b(status|check).*\bleave\s+#?\d+\b|"
        r"\bleave\s+#?\d+.*\bstatus\b|"
        r"\bleave\s+(balance|history)\b|"
        r"\bpending\s+(leaves|approvals)\b|"
        r"\b(leave\s+policy|leave\s+rules)\b|"
        r"\bapply\s+.*\bleave\b|"
        r"\b(sick|casual|earned)\s+leave\b|"
        r"\btime\s+off\b|\bvacation\b",
        msg_lower,
    ):
        return "hr"

    # Company / general info — check BEFORE IT so "who is the CEO",
    # "tell me about the company", "organization name" etc. don't get
    # captured by overly broad IT keywords.
    if re.search(
        r"\b(ceo|company|organi[sz]ation|founder|headquarter(?:ed|s)?|about us|tell me about|our mission|values|founded)\b",
        msg_lower,
    ):
        return "general"

    # Deterministic IT routing. NOTE: the closing alternative MUST NOT be
    # empty (``software|)``) — that would let an empty-string alternative
    # match every message and force every query into IT. End the list
    # with a real keyword.
    if re.search(
        r"\b("
        r"ticket(s)?|"
        r"laptop|"
        r"password reset|password|"
        r"wifi|wi-fi|network|vpn|"
        r"monitor|keyboard|mouse|printer|"
        r"system error|"
        r"asset request|asset(s)?|"
        r"software license|software"
        r")\b",
        msg_lower,
    ):
        return "it"

    # Use Gemini Flash for intelligent classification, with a Groq fallback
    # if Gemini is rate-limited / quota-exhausted.
    try:
        llm = get_llm("gemini_flash")
    except Exception as exc:
        print(f"[router_agent] gemini_flash unavailable, falling back to groq: {exc}")
        llm = get_llm("groq_fast")

    prompt = f"""
    You are an enterprise query classifier. 
    Classify the following user message into exactly one category: "hr", "it", or "general".

    - "hr": Leave requests, policy questions, resignation, payroll, benefits.
    - "it": Hardware issues, software access, network/VPN, tickets, asset requests.
    - "general": Greetings, company info (CEO, name), or unrelated talk.

    Message: "{normalized_msg}"

    Return ONLY JSON:
    {{
      "agent": "hr" | "it" | "general",
      "reason": "brief explanation"
    }}
    """

    try:
        response = llm.invoke(prompt)
        raw = response.content.strip()
        cleaned = _clean_json(raw)
        data = json.loads(cleaned)
        agent = (data.get("agent") or "general").strip().lower()
        
        if agent not in {"hr", "it", "general"}:
            return "general"
        return agent

    except Exception as e:
        print(f"[router_agent] gemini classification failed: {e} — trying groq")
        try:
            groq_llm = get_llm("groq_fast")
            response = groq_llm.invoke(prompt)
            raw = response.content.strip()
            cleaned = _clean_json(raw)
            data = json.loads(cleaned)
            agent = (data.get("agent") or "general").strip().lower()
            if agent in {"hr", "it", "general"}:
                return agent
        except Exception as e2:
            print(f"[router_agent] groq fallback also failed: {e2}")
        return "general"
