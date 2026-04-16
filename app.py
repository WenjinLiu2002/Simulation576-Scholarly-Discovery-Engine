"""
Scholarly Discovery Engine
MASC 576 Discussion #2 - Snowballing Literature Review Web App
"""

import streamlit as st
import requests
import json
import re
import random
import xml.etree.ElementTree as ET
from pyvis.network import Network
import streamlit.components.v1 as components
from datetime import datetime

# ─────────────────────────────────────────────
#  PAGE CONFIG
# ─────────────────────────────────────────────
st.set_page_config(
    page_title="Scholarly Discovery Engine",
    page_icon="🔭",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ─────────────────────────────────────────────
#  CUSTOM CSS
# ─────────────────────────────────────────────
st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Space+Mono:wght@400;700&family=DM+Sans:wght@300;400;500;600&display=swap');

html, body, [class*="css"] {
    font-family: 'DM Sans', sans-serif;
}

/* Dark academic theme */
.stApp {
    background: #0d1117;
    color: #e6edf3;
}

h1, h2, h3 { font-family: 'Space Mono', monospace; }

.stButton>button {
    background: linear-gradient(135deg, #1f6feb, #388bfd);
    color: white;
    border: none;
    border-radius: 6px;
    font-family: 'Space Mono', monospace;
    font-size: 13px;
    padding: 0.5rem 1.2rem;
    transition: all 0.2s;
}
.stButton>button:hover {
    transform: translateY(-1px);
    box-shadow: 0 4px 15px rgba(31,111,235,0.4);
}

.paper-card {
    background: #161b22;
    border: 1px solid #30363d;
    border-radius: 10px;
    padding: 1rem 1.2rem;
    margin: 0.5rem 0;
    cursor: pointer;
    transition: all 0.2s;
}
.paper-card:hover {
    border-color: #1f6feb;
    box-shadow: 0 0 12px rgba(31,111,235,0.25);
}
.paper-card h4 {
    color: #58a6ff;
    margin: 0 0 0.3rem 0;
    font-size: 14px;
    font-family: 'Space Mono', monospace;
}
.paper-card p {
    color: #8b949e;
    font-size: 12px;
    margin: 0;
}
.paper-card .meta {
    color: #3fb950;
    font-size: 11px;
    font-family: 'Space Mono', monospace;
    margin-top: 0.4rem;
}

.badge {
    display: inline-block;
    padding: 2px 8px;
    border-radius: 20px;
    font-size: 11px;
    font-family: 'Space Mono', monospace;
    margin-right: 4px;
}
.badge-seed { background: #1f6feb33; color: #58a6ff; border: 1px solid #1f6feb; }
.badge-forward { background: #2ea04333; color: #3fb950; border: 1px solid #2ea043; }
.badge-backward { background: #d29922333; color: #d29922; border: 1px solid #d29922; }

.stat-box {
    background: #161b22;
    border: 1px solid #30363d;
    border-radius: 8px;
    padding: 0.8rem;
    text-align: center;
}
.stat-box .num {
    font-family: 'Space Mono', monospace;
    font-size: 1.8rem;
    color: #58a6ff;
}
.stat-box .label {
    font-size: 11px;
    color: #8b949e;
    text-transform: uppercase;
    letter-spacing: 1px;
}

.graph-container {
    background: #0d1117;
    border: 1px solid #30363d;
    border-radius: 10px;
    overflow: hidden;
}
</style>
""", unsafe_allow_html=True)

# ─────────────────────────────────────────────
#  HELPERS
# ─────────────────────────────────────────────

FIELD_COLORS = {
    "cs": "#1f6feb",       # Blue  - Computer Science
    "physics": "#d29922",  # Gold  - Physics
    "cond-mat": "#a371f7", # Purple - Condensed Matter
    "math": "#3fb950",     # Green - Math
    "astro": "#ff7b72",    # Red   - Astrophysics
    "quant-ph": "#f78166", # Coral - Quantum
    "eess": "#79c0ff",     # Sky   - Electrical Eng
    "other": "#8b949e",    # Gray  - Other
}

def get_field_color(arxiv_id_or_category: str) -> str:
    s = arxiv_id_or_category.lower()
    for key in FIELD_COLORS:
        if key in s:
            return FIELD_COLORS[key]
    return FIELD_COLORS["other"]

def get_field_label(category: str) -> str:
    cat = category.lower()
    if "cs" in cat: return "CS / AI"
    if "cond-mat" in cat: return "Cond. Matter"
    if "physics" in cat: return "Physics"
    if "math" in cat: return "Math"
    if "astro" in cat: return "Astrophysics"
    if "quant-ph" in cat: return "Quantum"
    if "eess" in cat: return "Elec. Eng."
    return "Other"

OPENALEX_BASE = "https://api.openalex.org"
OA_HEADERS = {"User-Agent": "ScholarlyDiscoveryEngine/1.0 (mailto:student@usc.edu)"}

def _oa_abstract(inverted_index: dict) -> str:
    """Reconstruct abstract from OpenAlex inverted index format."""
    if not inverted_index:
        return "No abstract available."
    words = {}
    for word, positions in inverted_index.items():
        for pos in positions:
            words[pos] = word
    return " ".join(words[i] for i in sorted(words))

def _oa_to_node(work: dict, node_type: str = "seed") -> dict:
    """Convert an OpenAlex work dict to our standard node format."""
    # ID
    oa_id = work.get("id", "").replace("https://openalex.org/", "")
    # ArXiv PDF link if available
    locs = work.get("locations") or []
    pdf_url = "#"
    for loc in locs:
        src = loc.get("source") or {}
        if "arxiv" in (src.get("display_name") or "").lower() or "arxiv" in (loc.get("landing_page_url") or "").lower():
            pdf_url = loc.get("pdf_url") or loc.get("landing_page_url") or "#"
            break
    if pdf_url == "#":
        oa_pdf = (work.get("open_access") or {}).get("oa_url") or "#"
        pdf_url = oa_pdf
    # Authors
    authors = [
        (a.get("author") or {}).get("display_name", "")
        for a in (work.get("authorships") or [])[:3]
    ]
    # Topic / field
    topics = work.get("topics") or []
    primary_cat = topics[0].get("field", {}).get("display_name", "other").lower() if topics else "other"
    # Abstract
    abstract = _oa_abstract(work.get("abstract_inverted_index"))
    return {
        "id": oa_id,
        "title": work.get("display_name") or work.get("title") or "Unknown Title",
        "authors": [a for a in authors if a],
        "abstract": (abstract[:400] + "...") if len(abstract) > 400 else abstract,
        "year": work.get("publication_year") or 0,
        "url": pdf_url,
        "categories": [primary_cat],
        "primary_category": primary_cat,
        "citations": work.get("cited_by_count") or 0,
        "node_type": node_type,
        "oa_id": oa_id,
    }

def search_arxiv(query: str, max_results: int = 5):
    """Search papers using OpenAlex API (no rate limits, no API key needed)."""
    try:
        resp = requests.get(
            f"{OPENALEX_BASE}/works",
            params={
                "search": query,
                "per_page": max_results,
                "select": "id,display_name,authorships,publication_year,abstract_inverted_index,"
                          "cited_by_count,open_access,locations,topics",
            },
            headers=OA_HEADERS,
            timeout=15,
        )
        if resp.status_code == 200:
            works = resp.json().get("results", [])
            return [_oa_to_node(w, "seed") for w in works if w.get("display_name")]
        else:
            st.error(f"OpenAlex search failed (status {resp.status_code}). Please try again.")
            return []
    except Exception as e:
        st.error(f"Search error: {e}")
        return []

def fetch_semantic_scholar(oa_id: str):
    """Fetch references and citations for a paper using OpenAlex."""
    # We store the full OpenAlex ID in the node; re-add prefix if needed
    full_id = oa_id if oa_id.startswith("W") else oa_id
    try:
        resp = requests.get(
            f"{OPENALEX_BASE}/works/{full_id}",
            params={"select": "id,display_name,referenced_works,cited_by_api_url,"
                              "cited_by_count,abstract_inverted_index,authorships,"
                              "publication_year,topics,open_access,locations"},
            headers=OA_HEADERS,
            timeout=15,
        )
        if resp.status_code == 200:
            return resp.json()
    except Exception:
        pass
    return None

def build_paper_node(paper: dict, node_type: str = "seed") -> dict:
    """Build a standardized node dict (pass-through since _oa_to_node already does this)."""
    node = dict(paper)
    node["node_type"] = node_type
    return node

def snowball_from_semantic(oa_data: dict, depth: int = 1) -> tuple[list, list]:
    """Extract references (backward) and citations (forward) using OpenAlex data."""
    nodes = []
    edges = []
    seed_oa_id = oa_data.get("id", "").replace("https://openalex.org/", "")

    # ── BACKWARD: papers this paper references ──
    ref_ids = oa_data.get("referenced_works", [])[:10]
    if ref_ids:
        # Batch fetch up to 10 referenced works
        ids_param = "|".join(r.replace("https://openalex.org/", "") for r in ref_ids)
        try:
            resp = requests.get(
                f"{OPENALEX_BASE}/works",
                params={
                    "filter": f"openalex_id:{ids_param}",
                    "per_page": 10,
                    "select": "id,display_name,authorships,publication_year,cited_by_count,topics,open_access,locations",
                },
                headers=OA_HEADERS,
                timeout=15,
            )
            if resp.status_code == 200:
                for w in resp.json().get("results", []):
                    n = _oa_to_node(w, "backward")
                    nodes.append(n)
                    edges.append((seed_oa_id, n["id"], "cites"))
        except Exception:
            pass

    # ── FORWARD: papers that cite this paper ──
    # Build the cited_by URL from the OpenAlex ID directly (more reliable)
    cited_by_url = oa_data.get("cited_by_api_url") or f"{OPENALEX_BASE}/works?filter=cites:{seed_oa_id}"
    try:
        resp = requests.get(
            cited_by_url,
            params={
                "per_page": 10,
                "sort": "cited_by_count:desc",
                "select": "id,display_name,authorships,publication_year,cited_by_count,topics,open_access,locations",
            },
            headers=OA_HEADERS,
            timeout=15,
        )
        if resp.status_code == 200:
            for w in resp.json().get("results", []):
                n = _oa_to_node(w, "forward")
                nodes.append(n)
                edges.append((n["id"], seed_oa_id, "cites"))
    except Exception:
        pass

    return nodes, edges


def build_pyvis_graph(seed_node: dict, neighbor_nodes: list, edges: list,
                       min_year: int, max_year: int,
                       filter_same_author: bool = False) -> str:
    """Build interactive Pyvis HTML graph and return as HTML string."""
    net = Network(
        height="580px", width="100%",
        bgcolor="#0d1117", font_color="#e6edf3",
        heading="",
    )
    net.set_options("""
    {
      "nodes": {
        "borderWidth": 2,
        "shadow": {"enabled": true, "size": 10}
      },
      "edges": {
        "smooth": {"type": "continuous"},
        "arrows": {"to": {"enabled": true, "scaleFactor": 0.5}},
        "color": {"color": "#30363d", "highlight": "#58a6ff"},
        "width": 1.5
      },
      "physics": {
        "forceAtlas2Based": {
          "gravitationalConstant": -80,
          "centralGravity": 0.005,
          "springLength": 150,
          "springConstant": 0.05
        },
        "solver": "forceAtlas2Based",
        "stabilization": {"iterations": 150}
      },
      "interaction": {
        "hover": true,
        "tooltipDelay": 100,
        "hideEdgesOnDrag": true
      }
    }
    """)

    def node_size(citations):
        return max(15, min(60, 15 + citations / 10))

    def make_tooltip(n):
        authors = ", ".join(n["authors"][:2]) or "Unknown"
        return (
            f"<div style='max-width:280px;background:#161b22;padding:12px;"
            f"border:1px solid #30363d;border-radius:8px;font-family:DM Sans,sans-serif'>"
            f"<b style='color:#58a6ff;font-size:13px'>{n['title'][:80]}...</b><br>"
            f"<span style='color:#8b949e;font-size:11px'>👤 {authors} · 📅 {n['year']}</span><br>"
            f"<span style='color:#3fb950;font-size:11px'>🔗 Cited by ~{n['citations']}</span><br>"
            f"<hr style='border-color:#30363d;margin:6px 0'>"
            f"<span style='color:#c9d1d9;font-size:11px'>{n['abstract'][:200]}...</span>"
            f"</div>"
        )

    # Collect all author names for same-author filter
    seed_authors = set(seed_node.get("authors", []))

    # Add seed node
    net.add_node(
        seed_node["id"],
        label=seed_node["title"][:30] + "…",
        title=make_tooltip(seed_node),
        color={"background": "#ffd700", "border": "#ffa500", "highlight": {"background": "#ffe44d"}},
        size=40,
        shape="star",
        url=seed_node["url"],
        font={"size": 14, "bold": True},
    )

    added_ids = {seed_node["id"]}

    # Add neighbor nodes
    for n in neighbor_nodes:
        if n["year"] and n["year"] > 0 and (n["year"] < min_year or n["year"] > max_year):
            continue
        if filter_same_author:
            paper_authors = set(n.get("authors", []))
            if not paper_authors.intersection(seed_authors):
                continue

        color_hex = get_field_color(n.get("primary_category", "other"))
        size = node_size(n.get("citations", 10))

        if n["id"] not in added_ids:
            net.add_node(
                n["id"],
                label=n["title"][:25] + "…",
                title=make_tooltip(n),
                color={"background": color_hex, "border": "#0d1117",
                       "highlight": {"background": color_hex}},
                size=size,
                url=n.get("url", "#"),
            )
            added_ids.add(n["id"])

    # Add edges
    for src, dst, label in edges:
        if src in added_ids and dst in added_ids:
            edge_color = "#2ea043" if label == "cited_by" else "#d29922"
            net.add_edge(src, dst, color=edge_color, title=label)

    html = net.generate_html()
    return html


# ─────────────────────────────────────────────
#  SESSION STATE INIT
# ─────────────────────────────────────────────
if "search_results" not in st.session_state:
    st.session_state.search_results = []
if "seed_paper" not in st.session_state:
    st.session_state.seed_paper = None
if "graph_nodes" not in st.session_state:
    st.session_state.graph_nodes = []
if "graph_edges" not in st.session_state:
    st.session_state.graph_edges = []
if "graph_built" not in st.session_state:
    st.session_state.graph_built = False


# ─────────────────────────────────────────────
#  SIDEBAR — FILTERS
# ─────────────────────────────────────────────
with st.sidebar:
    st.markdown("## 🔭 Scholarly Discovery")
    st.markdown("*Snowballing literature map*")
    st.markdown("---")

    st.markdown("### ⚙️ Snowball Depth")
    depth = st.slider("Generations to follow", 1, 3, 1,
                      help="Level 1 = direct refs/cites. Level 2 = refs of refs. (Warning: Level 3 is slow!)")

    st.markdown("### 🗓️ Year Filter")
    year_range = st.slider("Publication year range", 1990, datetime.now().year,
                           (1990, datetime.now().year))

    st.markdown("### 🔗 Connection Filters")
    filter_same_author = st.checkbox("Show only papers by same author(s)", value=False)

    st.markdown("---")
    st.markdown("### 🎨 Field Color Key")
    for field, color in FIELD_COLORS.items():
        st.markdown(
            f"<span style='background:{color};border-radius:4px;padding:2px 10px;"
            f"font-size:11px;color:white;font-family:monospace'>● {field.upper()}</span>",
            unsafe_allow_html=True
        )
    st.markdown("<span style='background:#ffd700;border-radius:4px;padding:2px 10px;"
                "font-size:11px;color:#0d1117;font-family:monospace'>★ SEED PAPER</span>",
                unsafe_allow_html=True)


# ─────────────────────────────────────────────
#  MAIN PANEL
# ─────────────────────────────────────────────
st.markdown("# 🔭 Scholarly Discovery Engine")
st.markdown("*Automate snowballing literature review via arXiv + Semantic Scholar*")
st.markdown("---")

# ── STEP 1: SEARCH ──────────────────────────
col_search, col_btn = st.columns([4, 1])
with col_search:
    query = st.text_input("", placeholder="Search: e.g. 'machine learning interatomic potential' or paste arXiv ID",
                          label_visibility="collapsed")
with col_btn:
    search_clicked = st.button("🔍 Search arXiv", use_container_width=True)

if search_clicked and query.strip():
    with st.spinner("Searching arXiv..."):
        st.session_state.search_results = search_arxiv(query.strip(), max_results=5)
        st.session_state.seed_paper = None
        st.session_state.graph_built = False

# ── STEP 2: SHOW RESULTS ────────────────────
if st.session_state.search_results and not st.session_state.seed_paper:
    st.markdown("### 📋 Top Results — Pick Your Seed Paper")
    for i, paper in enumerate(st.session_state.search_results):
        authors_str = ", ".join(paper["authors"]) + (" et al." if len(paper["authors"]) >= 3 else "")
        field_label = get_field_label(paper["primary_category"])
        st.markdown(f"""
        <div class="paper-card">
            <h4>[{i+1}] {paper['title']}</h4>
            <p>{authors_str} · {paper['year']}</p>
            <p style="margin-top:4px;color:#c9d1d9;font-size:12px">{paper['abstract'][:200]}...</p>
            <div class="meta">📂 {field_label} &nbsp;·&nbsp; arXiv:{paper['id']}</div>
        </div>
        """, unsafe_allow_html=True)
        if st.button(f"⭐ Start Map from Paper #{i+1}", key=f"pick_{i}"):
            st.session_state.seed_paper = build_paper_node(paper, "seed")
            st.session_state.graph_built = False
            st.rerun()

# ── STEP 3: SEED SELECTED — SNOWBALL ────────
if st.session_state.seed_paper:
    seed = st.session_state.seed_paper
    st.markdown("---")
    st.markdown("### 🌱 Seed Paper Selected")
    st.markdown(f"""
    <div class="paper-card" style="border-color:#ffd700">
        <h4 style="color:#ffd700">★ {seed['title']}</h4>
        <p>{", ".join(seed['authors'])}</p>
        <p style="margin-top:4px;color:#c9d1d9;font-size:12px">{seed['abstract'][:300]}...</p>
        <div class="meta">OpenAlex:{seed['id']} · <a href="{seed['url']}" target="_blank" style="color:#58a6ff">Open PDF ↗</a></div>
    </div>
    """, unsafe_allow_html=True)

    col_expand, col_reset = st.columns([3, 1])
    with col_expand:
        expand_clicked = st.button("🔁 Expand: Snowball This Paper!", use_container_width=True)
    with col_reset:
        if st.button("↩ Reset", use_container_width=True):
            st.session_state.seed_paper = None
            st.session_state.graph_built = False
            st.session_state.search_results = []
            st.rerun()

    if expand_clicked:
        with st.spinner("🕸️ Fetching references and citations from OpenAlex..."):
            oa_data = fetch_semantic_scholar(seed["id"])
            if oa_data:
                nodes, edges = snowball_from_semantic(oa_data, depth=depth)
                seed["citations"] = oa_data.get("cited_by_count", seed["citations"])
                st.session_state.graph_nodes = nodes
                st.session_state.graph_edges = edges
                st.session_state.graph_built = True
                st.success(f"✅ Found {len(nodes)} related papers via OpenAlex!")
            else:
                # Fallback: search for related papers by title
                st.warning("⚠️ Could not fetch full paper data — using related search fallback.")
                related = search_arxiv(seed["title"][:60], max_results=10)
                nodes = [build_paper_node(p, "backward") for p in related if p["id"] != seed["id"]]
                edges = [(seed["id"], n["id"], "related") for n in nodes]
                st.session_state.graph_nodes = nodes
                st.session_state.graph_edges = edges
                st.session_state.graph_built = True

    # ── STEP 4: GRAPH ───────────────────────
    if st.session_state.graph_built:
        nodes = st.session_state.graph_nodes
        edges = st.session_state.graph_edges

        # Stats row
        backward_count = sum(1 for n in nodes if n.get("node_type") == "backward")
        forward_count = sum(1 for n in nodes if n.get("node_type") == "forward")

        c1, c2, c3, c4 = st.columns(4)
        with c1:
            st.markdown(f'<div class="stat-box"><div class="num">1</div><div class="label">Seed Paper</div></div>', unsafe_allow_html=True)
        with c2:
            st.markdown(f'<div class="stat-box"><div class="num">{backward_count}</div><div class="label">References (↩)</div></div>', unsafe_allow_html=True)
        with c3:
            st.markdown(f'<div class="stat-box"><div class="num">{forward_count}</div><div class="label">Citing Papers (→)</div></div>', unsafe_allow_html=True)
        with c4:
            st.markdown(f'<div class="stat-box"><div class="num">{seed["citations"]}</div><div class="label">Seed Citations</div></div>', unsafe_allow_html=True)

        st.markdown("")

        # Build and render the graph
        st.markdown("### 🕸️ Citation Map")
        st.caption("Hover over nodes to see abstract & metadata. Node size = citation count. ★ = seed paper.")
        with st.spinner("Rendering graph..."):
            html_graph = build_pyvis_graph(
                seed_node=seed,
                neighbor_nodes=nodes,
                edges=edges,
                min_year=year_range[0],
                max_year=year_range[1],
                filter_same_author=filter_same_author,
            )

        st.markdown('<div class="graph-container">', unsafe_allow_html=True)
        components.html(html_graph, height=600, scrolling=False)
        st.markdown('</div>', unsafe_allow_html=True)

        # ── STEP 5: PAPER LIST TABLE ─────────
        st.markdown("---")
        st.markdown("### 📄 All Discovered Papers")

        type_filter = st.selectbox("Filter by type", ["All", "Backward (references)", "Forward (citations)"])

        for n in nodes:
            if type_filter == "Backward (references)" and n.get("node_type") != "backward":
                continue
            if type_filter == "Forward (citations)" and n.get("node_type") != "forward":
                continue
            if n["year"] and n["year"] > 0 and (n["year"] < year_range[0] or n["year"] > year_range[1]):
                continue

            badge_class = "badge-backward" if n.get("node_type") == "backward" else "badge-forward"
            badge_text = "↩ Reference" if n.get("node_type") == "backward" else "→ Cites Seed"
            authors_str = ", ".join(n["authors"][:2])

            st.markdown(f"""
            <div class="paper-card">
                <span class="badge {badge_class}">{badge_text}</span>
                <h4 style="margin-top:6px">{n['title']}</h4>
                <p>{authors_str} · {n['year']} · ~{n['citations']} citations</p>
                <p style="margin-top:4px;color:#c9d1d9;font-size:12px">{n['abstract'][:200]}...</p>
                <div class="meta">
                    <a href="{n['url']}" target="_blank" style="color:#58a6ff">Open PDF ↗</a>
                </div>
            </div>
            """, unsafe_allow_html=True)

# ── FOOTER ──────────────────────────────────
st.markdown("---")
st.markdown(
    "<p style='text-align:center;color:#484f58;font-size:11px;font-family:Space Mono,monospace'>"
    "MASC 576 · Discussion #2 · Scholarly Discovery Engine · arXiv + Semantic Scholar API"
    "</p>",
    unsafe_allow_html=True,
)
