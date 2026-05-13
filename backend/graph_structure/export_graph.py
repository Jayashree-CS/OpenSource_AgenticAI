from pathlib import Path
from graph_structure.graph import build_graph

def export_graph():
    app = build_graph()
    graph = app.get_graph()

    output_dir = Path(__file__).parent

    # Save Mermaid source
    mmd_text = graph.draw_mermaid()
    mmd_file = output_dir / "workflow_graph.mmd"

    with open(mmd_file, "w", encoding="utf-8") as f:
        f.write(mmd_text)

    # Save PNG
    png_bytes = graph.draw_mermaid_png()
    png_file = output_dir / "workflow_graph.png"

    with open(png_file, "wb") as f:
        f.write(png_bytes)

    print(f"Saved: {mmd_file}")
    print(f"Saved: {png_file}")

if __name__ == "__main__":
    export_graph()