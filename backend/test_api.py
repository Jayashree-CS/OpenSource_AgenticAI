

try:
    import google.generativeai as genai
except ImportError as e:
    raise ImportError(
        "The google.generativeai package is not installed. "
        "Install it with: pip install google-generativeai"
    ) from e

genai.configure(api_key="AIzaSyA1CbRZpS1VDjPB06DmIMPqrgvc06irhLQ")

for m in genai.list_models():
    print(m.name)