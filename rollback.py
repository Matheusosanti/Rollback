import pandas as pd
import streamlit as st
import plotly.express as px

# ============================
# Configuração da Página
# ============================
st.set_page_config(page_title="Resumo Rollbacks", layout="wide")

st.markdown(
    """
    <style>
      .block-container { padding-top: 1.2rem; padding-bottom: 2rem; }
      div[data-testid="metric-container"] {
        background: rgba(255,255,255,0.04);
        border: 1px solid rgba(255,255,255,0.08);
        padding: 14px 14px 10px 14px;
        border-radius: 14px;
      }
      .soft-card {
        background: rgba(255,255,255,0.03);
        border: 1px solid rgba(255,255,255,0.08);
        padding: 14px;
        border-radius: 14px;
      }
      .muted { opacity: 0.75; }
      .brand-badge {
        display:inline-block;
        padding: 6px 10px;
        border-radius: 999px;
        font-weight: 600;
        font-size: 12px;
        margin-right: 8px;
      }
    </style>
    """,
    unsafe_allow_html=True,
)

st.title("🔁 Rollbacks — Resumo por Brand")
st.caption("Conta rollback por reference única e gera resumo por brand (cliente+jogo, horários e jogos).")

# ============================
# Helpers
# ============================
def norm_cols(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    df.columns = [str(c).strip() for c in df.columns]
    return df

def coerce_user_id(series: pd.Series) -> pd.Series:
    s = series.astype(str)
    s = s.str.replace(r"\.0$", "", regex=True)
    s = s.replace(["nan", "None", "NaT"], pd.NA)
    return s.str.strip()

def kpi_int(n: int) -> str:
    return f"{int(n):,}".replace(",", ".")

@st.cache_data(show_spinner=False, ttl=1800)
def load_file(uploaded_file, sheet_name: str | None):
    name = uploaded_file.name.lower()
    if name.endswith(".csv"):
        return pd.read_csv(uploaded_file)
    if sheet_name:
        return pd.read_excel(uploaded_file, sheet_name=sheet_name)
    return pd.read_excel(uploaded_file)

def require_cols(df: pd.DataFrame, required: list[str]) -> dict[str, str]:
    cols_lower = {c.lower().strip(): c for c in df.columns}
    missing = [c for c in required if c not in cols_lower]
    if missing:
        raise ValueError(
            f"Colunas obrigatórias não encontradas: {missing}. Necessário: {', '.join(required)}"
        )
    return {k: cols_lower[k] for k in required}

def normalize_brand(s: pd.Series) -> pd.Series:
    # normaliza espaços e caixa
    x = s.astype(str).str.strip()
    # padroniza variações comuns
    x_lower = x.str.lower()
    x = x_lower.replace({
        "7k": "7K",
        "7kbet": "7K",
        "7kbetbr": "7K",
        "cassino": "Cassino",
        "cassinobet": "Cassino",
        "cassinobetbr": "Cassino",
        "vera": "Vera",
        "verabet": "Vera",
        "verabetbr": "Vera",
    })
    # mantém Sem Brand quando vier vazio/nan
    x = x.replace(["nan", "none", ""], "Sem Brand")
    return x

# ============================
# Sidebar (config)
# ============================
st.sidebar.header("⚙️ Configurações")

bucket = st.sidebar.selectbox(
    "Agrupar horários por",
    ["Minuto", "Hora"],
    index=0
)
freq = {"Hora": "H", "Minuto": "T"}[bucket]

top_n_games_global = st.sidebar.slider("Top jogos (geral)", 5, 50, 20, 1)
top_n_games_brand = st.sidebar.slider("Top jogos (por brand)", 5, 50, 15, 1)

# Cores por brand
cores_brand = {
    "7K": "#34A853",
    "Vera": "#0F9D58",
    "Cassino": "#1A73E8",
    "Sem Brand": "#999999",
}

ordem_brands_default = ["7K", "Cassino", "Vera", "Sem Brand"]
ordem_brands = st.sidebar.multiselect(
    "Ordem preferida das brands",
    options=ordem_brands_default,
    default=["7K", "Cassino", "Vera"],
)

# ============================
# Upload
# ============================
uploaded = st.file_uploader("📤 Envie a BASE (.xlsx/.xls) ou CSV", type=["xlsx", "xls", "csv"])
if uploaded is None:
    st.info("Envie a planilha para começar.")
    st.stop()

sheet_name = None
if uploaded.name.lower().endswith((".xlsx", ".xls")):
    with st.expander("📄 Opções do Excel", expanded=False):
        sheet_name_input = st.text_input("Nome da aba (ex.: BASE). Vazio = primeira aba", value="BASE").strip()
        sheet_name = sheet_name_input if sheet_name_input else None

with st.spinner("Lendo arquivo..."):
    df = load_file(uploaded, sheet_name=sheet_name)
df = norm_cols(df)

# ============================
# Validação e limpeza
# ============================
required = ["user_id", "game_name", "reference", "created_at", "brand_name"]
try:
    colmap = require_cols(df, required)
except ValueError as e:
    st.error(str(e))
    st.stop()

df = df[[colmap["user_id"], colmap["game_name"], colmap["reference"], colmap["created_at"], colmap["brand_name"]]].copy()
df.columns = ["user_id", "game_name", "reference", "created_at", "brand_name"]

df["user_id"] = coerce_user_id(df["user_id"])
df["game_name"] = df["game_name"].astype(str).replace(["nan", "None"], pd.NA).str.strip()
df["reference"] = df["reference"].astype(str).replace(["nan", "None"], pd.NA).str.strip()

# brand robusto
df["brand_name"] = normalize_brand(df["brand_name"])

# created_at
df["created_at"] = pd.to_datetime(df["created_at"], errors="coerce", utc=True)

# remove inválidos
df = df.dropna(subset=["reference", "created_at"])
df = df[df["reference"].astype(str).str.len() > 0]

if df.empty:
    st.warning("A BASE não tem linhas válidas com reference e created_at.")
    st.stop()

# ============================
# Filtros
# ============================
st.sidebar.header("🔎 Filtros")

brands_opts = sorted(df["brand_name"].unique().tolist())
f_brand = st.sidebar.multiselect("Filtrar brand", options=brands_opts, default=[])

f_user = st.sidebar.text_input("Filtrar user_id contém", value="").strip()
f_game = st.sidebar.text_input("Filtrar game_name contém", value="").strip()

dff = df.copy()
if f_brand:
    dff = dff[dff["brand_name"].isin(f_brand)]
if f_user:
    dff = dff[dff["user_id"].astype(str).str.contains(f_user, case=False, na=False)]
if f_game:
    dff = dff[dff["game_name"].astype(str).str.contains(f_game, case=False, na=False)]

if dff.empty:
    st.warning("Nenhum dado após aplicar filtros.")
    st.stop()

# ============================
# PROCESSAMENTO (reference única = rollback)
# ============================
refs_brand = dff.drop_duplicates(subset=["brand_name", "reference"]).copy()

cliente_jogo = (
    dff.dropna(subset=["user_id", "game_name", "reference"])
       .drop_duplicates(subset=["brand_name", "user_id", "game_name", "reference"])
       .groupby(["brand_name", "user_id", "game_name"], as_index=False)
       .agg(qtd_rollbacks=("reference", "count"))
       .sort_values("qtd_rollbacks", ascending=False)
)

refs_brand["bucket_time"] = refs_brand["created_at"].dt.floor(freq)
horarios = (
    refs_brand.groupby(["brand_name", "bucket_time"], as_index=False)
             .agg(qtd_rollbacks=("reference", "count"))
             .sort_values("qtd_rollbacks", ascending=False)
)
horarios["horario_utc"] = horarios["bucket_time"].dt.strftime("%d/%m/%Y %H:%M")

jogos = (
    refs_brand.dropna(subset=["game_name"])
             .groupby(["brand_name", "game_name"], as_index=False)
             .agg(qtd_rollbacks=("reference", "count"))
             .sort_values("qtd_rollbacks", ascending=False)
)

top_jogos_geral = (
    jogos.groupby("game_name", as_index=False)["qtd_rollbacks"]
         .sum()
         .sort_values("qtd_rollbacks", ascending=False)
)

# ============================
# KPIs (igual seu resumo)
# ============================
total_rollbacks = int(refs_brand.groupby("brand_name")["reference"].nunique().sum())
total_usuario_jogo = int(cliente_jogo.shape[0])
total_horarios = int(horarios.shape[0])
total_jogos = int(jogos.groupby("brand_name")["game_name"].nunique().sum())

k1, k2, k3, k4 = st.columns(4)
k1.metric("🔁 Rollbacks", kpi_int(total_rollbacks))
k2.metric("👤 Usuários/Jogos", kpi_int(total_usuario_jogo))
k3.metric(f"🕒 Horários ({bucket})", kpi_int(total_horarios))
k4.metric("🎮 Jogos", kpi_int(total_jogos))

st.markdown(
    """
    <div class="soft-card">
      <b>📌 Regra</b><br/><br/>
      • Rollback = <b>reference única</b>.<br/>
      • Horários/Jogos usam <b>reference única por brand</b>.<br/>
      • Usuários/Jogos conta referências únicas em cada par (<b>user_id + game_name</b>) dentro da brand.
    </div>
    """,
    unsafe_allow_html=True,
)

st.divider()

# ============================
# TOP Jogos (GERAL)
# ============================
st.subheader("🏆 Top Jogos com Rollback (Geral)")

colA, colB = st.columns([1.2, 1])

with colA:
    st.dataframe(top_jogos_geral.head(top_n_games_global), use_container_width=True, hide_index=True)

with colB:
    plot_base = top_jogos_geral.head(top_n_games_brand).copy()
    plot_base = plot_base.sort_values("qtd_rollbacks", ascending=True)
    fig_top = px.bar(plot_base, x="qtd_rollbacks", y="game_name", orientation="h", text="qtd_rollbacks")
    fig_top.update_traces(textposition="outside", cliponaxis=False)
    fig_top.update_layout(height=520, margin=dict(l=10, r=10, t=10, b=10),
                          xaxis_title="Qtd Rollbacks", yaxis_title="")
    st.plotly_chart(
        fig_top,
        use_container_width=True,
        config={"locale": "pt-BR"},
        key="chart_top_jogos_geral"
    )

st.download_button(
    "⬇️ Baixar Top Jogos (Geral) (CSV)",
    data=top_jogos_geral.to_csv(index=False).encode("utf-8"),
    file_name="rollback_top_jogos_geral.csv",
    mime="text/csv",
)

st.divider()

# ============================
# Tabs por Brand
# ============================
brands_presentes = dff["brand_name"].unique().tolist()

ordered = [b for b in ordem_brands if b in brands_presentes]
ordered += [b for b in brands_presentes if b not in ordered]

tabs = st.tabs([f"{b}" for b in ordered])

for idx, brand in enumerate(ordered):
    with tabs[idx]:
        cor = cores_brand.get(brand, "#999999")
        st.markdown(
            f'<span class="brand-badge" style="background:{cor};color:#fff;">{brand}</span>'
            f'<span class="muted">Resumo detalhado</span>',
            unsafe_allow_html=True
        )

        brand_refs = refs_brand[refs_brand["brand_name"] == brand]
        brand_cliente_jogo = cliente_jogo[cliente_jogo["brand_name"] == brand]
        brand_horarios = horarios[horarios["brand_name"] == brand]
        brand_jogos = jogos[jogos["brand_name"] == brand]

        total_brand_rollbacks = int(brand_refs["reference"].nunique())
        total_brand_usuario_jogo = int(brand_cliente_jogo.shape[0])
        total_brand_horarios = int(brand_horarios.shape[0])
        total_brand_jogos = int(brand_jogos["game_name"].nunique())

        c1, c2, c3, c4 = st.columns(4)
        c1.metric("🔁 Rollbacks", kpi_int(total_brand_rollbacks))
        c2.metric("👤 Usuários/Jogos", kpi_int(total_brand_usuario_jogo))
        c3.metric(f"🕒 Horários ({bucket})", kpi_int(total_brand_horarios))
        c4.metric("🎮 Jogos", kpi_int(total_brand_jogos))

        st.divider()

        # TOP jogos brand
        st.subheader(f"🏆 Top Jogos — {brand}")

        top_brand = brand_jogos.sort_values("qtd_rollbacks", ascending=False).copy()

        col1, col2 = st.columns([1.2, 1])
        with col1:
            st.dataframe(top_brand.head(top_n_games_brand), use_container_width=True, hide_index=True)

        with col2:
            plot_b = top_brand.head(top_n_games_brand).sort_values("qtd_rollbacks", ascending=True)
            fig_b = px.bar(plot_b, x="qtd_rollbacks", y="game_name", orientation="h", text="qtd_rollbacks")
            fig_b.update_traces(textposition="outside", cliponaxis=False)
            fig_b.update_layout(height=520, margin=dict(l=10, r=10, t=10, b=10),
                                xaxis_title="Qtd Rollbacks", yaxis_title="")
            st.plotly_chart(
                fig_b,
                use_container_width=True,
                config={"locale": "pt-BR"},
                key=f"chart_top_jogos_brand_{brand}"
            )

        st.download_button(
            f"⬇️ Baixar Top Jogos — {brand} (CSV)",
            data=top_brand.to_csv(index=False).encode("utf-8"),
            file_name=f"rollback_top_jogos_{brand}.csv",
            mime="text/csv",
        )

        st.divider()

        # Tabelas detalhadas
        tA, tB, tC = st.tabs(["👤 Cliente + Jogo", f"🕒 Horários ({bucket})", "🎮 Jogos (tabela)"])

        with tA:
            st.dataframe(brand_cliente_jogo, use_container_width=True, hide_index=True)
            st.download_button(
                "⬇️ Baixar Cliente+Jogo (CSV)",
                data=brand_cliente_jogo.to_csv(index=False).encode("utf-8"),
                file_name=f"rollback_{brand}_cliente_jogo.csv",
                mime="text/csv",
            )

        with tB:
            sub = brand_horarios[["horario_utc", "qtd_rollbacks"]].copy()
            st.dataframe(sub, use_container_width=True, hide_index=True)

            top_time = sub.head(50).sort_values("qtd_rollbacks", ascending=True)
            fig_time = px.bar(top_time, x="qtd_rollbacks", y="horario_utc", orientation="h", text="qtd_rollbacks")
            fig_time.update_traces(textposition="outside", cliponaxis=False)
            fig_time.update_layout(height=520, margin=dict(l=10, r=10, t=10, b=10),
                                   xaxis_title="Qtd Rollbacks", yaxis_title="")
            st.plotly_chart(
                fig_time,
                use_container_width=True,
                config={"locale": "pt-BR"},
                key=f"chart_horarios_{bucket}_{brand}"
            )

            st.download_button(
                "⬇️ Baixar Horários (CSV)",
                data=sub.to_csv(index=False).encode("utf-8"),
                file_name=f"rollback_{brand}_horarios_{bucket.lower()}.csv",
                mime="text/csv",
            )

        with tC:
            st.dataframe(brand_jogos, use_container_width=True, hide_index=True)
            st.download_button(
                "⬇️ Baixar Jogos (CSV)",
                data=brand_jogos.to_csv(index=False).encode("utf-8"),
                file_name=f"rollback_{brand}_jogos.csv",
                mime="text/csv",
            )

st.divider()

# ============================
# Downloads gerais
# ============================
st.subheader("⬇️ Downloads (Geral)")

down_h = horarios[["brand_name", "horario_utc", "qtd_rollbacks"]].copy()

d1, d2, d3, d4 = st.columns(4)
with d1:
    st.download_button(
        "Cliente+Jogo (geral)",
        data=cliente_jogo.to_csv(index=False).encode("utf-8"),
        file_name="rollback_geral_cliente_jogo.csv",
        mime="text/csv",
    )
with d2:
    st.download_button(
        f"Horários (geral) ({bucket})",
        data=down_h.to_csv(index=False).encode("utf-8"),
        file_name=f"rollback_geral_horarios_{bucket.lower()}.csv",
        mime="text/csv",
    )
with d3:
    st.download_button(
        "Jogos (geral por brand)",
        data=jogos.to_csv(index=False).encode("utf-8"),
        file_name="rollback_geral_jogos_por_brand.csv",
        mime="text/csv",
    )
with d4:
    st.download_button(
        "Top Jogos (geral)",
        data=top_jogos_geral.to_csv(index=False).encode("utf-8"),
        file_name="rollback_top_jogos_geral.csv",
        mime="text/csv",
    )
