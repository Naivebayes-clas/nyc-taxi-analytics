import streamlit as st
import pandas as pd
import psycopg2
import matplotlib.pyplot as plt
import seaborn as sns

st.set_page_config(page_title="NYC Taxi Analytics", layout="wide")
st.title("NYC Yellow Taxi Analytics (2023)")
st.caption("Advanced SQL analysis | PostgreSQL + Streamlit")

# --- Payment type mapping ---
PAYMENT_MAP = {
    "1": "Credit Card",
    "2": "Cash",
    "3": "No Charge",
    "4": "Dispute",
    "5": "Unknown",
    "6": "Vacant",
}

# --- DB Connection ---
@st.cache_resource
def get_conn():
    return psycopg2.connect(
        host="localhost", port=6544,
        user="taxi_user", password="taxi_pass",
        dbname="taxi"
    )

conn = get_conn()

def run_query(query):
    return pd.read_sql(query, conn)

# --- Sidebar ---
st.sidebar.header("Select Analysis")
sections = [
    "1. Fare by Hour & Day",
    "2. Top Pickup Zones",
    "3. Monthly Revenue Trend",
    "4. Most Common Routes",
    "5. Fare per Mile",
    "6. Longest Rides by Zone",
    "7. Outlier Trips",
    "8. Payment Method Breakdown",
]
selected = st.sidebar.radio("Query", sections)

# --- KPIs (always shown) ---
kpi_df = run_query("""
    SELECT
        COUNT(*) AS total_trips,
        ROUND(AVG(total_amount), 2) AS avg_fare,
        ROUND(SUM(total_amount), 2) AS total_revenue,
        ROUND(AVG(trip_distance), 2) AS avg_distance
    FROM yellow_taxi_2023
""")
c1, c2, c3, c4 = st.columns(4)
c1.metric("Total Trips", f"{kpi_df['total_trips'].iloc[0]:,}")
c2.metric("Avg Fare", f"${kpi_df['avg_fare'].iloc[0]}")
c3.metric("Total Revenue", f"${kpi_df['total_revenue'].iloc[0]:,.0f}")
c4.metric("Avg Distance", f"{kpi_df['avg_distance'].iloc[0]} mi")

st.divider()

# --- Section 1: Fare by Hour & Day ---
if selected == sections[0]:
    st.subheader("Average Fare by Hour & Day of Week")
    st.caption("Darker = higher average fare. Shows when drivers earn the most.")
    df = run_query("""
        SELECT
            EXTRACT(DOW FROM pickup_datetime) AS day,
            EXTRACT(HOUR FROM pickup_datetime) AS hour,
            COUNT(*) AS trips,
            ROUND(AVG(fare_amount), 2) AS avg_fare
        FROM yellow_taxi_2023
        GROUP BY 1, 2
        HAVING COUNT(*) >= 5
        ORDER BY 1, 2
    """)
    day_names = {0: 'Sun', 1: 'Mon', 2: 'Tue', 3: 'Wed', 4: 'Thu', 5: 'Fri', 6: 'Sat'}
    df['day_name'] = df['day'].map(lambda x: day_names.get(int(x), '?'))

    pivot = df.pivot_table(index='hour', columns='day_name', values='avg_fare')
    order = ['Sun', 'Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat']
    pivot = pivot.reindex(columns=[d for d in order if d in pivot.columns])

    fig, ax = plt.subplots(figsize=(12, 6))
    sns.heatmap(pivot, annot=True, fmt=".0f", cmap="YlOrRd", ax=ax,
                cbar_kws={'label': 'Avg Fare ($)'}, linewidths=0.5)
    ax.set_title("Avg Fare by Hour × Day of Week ($)", fontsize=13)
    ax.set_xlabel("Day of Week")
    ax.set_ylabel("Hour")
    st.pyplot(fig)

    # Insight
    max_cell = pivot.stack().idxmax()
    st.success(f"**Peak earning window:** {max_cell[1]} at {int(max_cell[0]):02d}:00 — avg fare ${pivot.stack().max():.0f}")

# --- Section 2: Top Pickup Zones ---
elif selected == sections[1]:
    st.subheader("Top 10 Pickup Zones by Trip Volume")
    st.caption("Where do the most taxi trips start?")
    df = run_query("""
        WITH zone_counts AS (
            SELECT
                z.zone_name,
                z.borough,
                COUNT(*) AS trips,
                ROUND(AVG(t.fare_amount), 2) AS avg_fare,
                RANK() OVER (ORDER BY COUNT(*) DESC) AS rnk
            FROM yellow_taxi_2023 t
            JOIN taxi_zones z ON t.pickup_zone = z.zone_id
            GROUP BY z.zone_name, z.borough
        )
        SELECT * FROM zone_counts WHERE rnk <= 10 ORDER BY rnk
    """)
    st.dataframe(df[['rnk', 'zone_name', 'borough', 'trips', 'avg_fare']],
                column_config={
                    'rnk': 'Rank',
                    'zone_name': 'Zone',
                    'borough': 'Borough',
                    'trips': 'Trips',
                    'avg_fare': 'Avg Fare ($)'
                }, hide_index=True)

    fig, ax = plt.subplots(figsize=(9, 5))
    display = df['zone_name'].str[:20]  # truncate long names
    ax.barh(display[::-1], df['trips'][::-1], color='#4A90D9')
    ax.set_xlabel("Trip Count")
    ax.set_title("Top 10 Pickup Zones")
    plt.tight_layout()
    st.pyplot(fig)

# --- Section 3: Monthly Revenue Trend ---
elif selected == sections[2]:
    st.subheader("Monthly Revenue")
    st.caption("Total revenue and trip count by month. Each bar represents ~1,000 sampled trips.")
    df = run_query("""
        SELECT
            date_trunc('month', pickup_datetime) AS month,
            COUNT(*) AS trips,
            ROUND(SUM(total_amount), 2) AS revenue,
            ROUND(AVG(total_amount), 2) AS avg_fare
        FROM yellow_taxi_2023
        GROUP BY 1
        ORDER BY 1
    """)
    df['month'] = pd.to_datetime(df['month'])
    df['month_label'] = df['month'].dt.strftime('%b %Y')

    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(12, 5))

    # Bar chart: Revenue
    ax1.bar(df['month_label'], df['revenue'], color='#4A90D9', edgecolor='white')
    ax1.set_ylabel("Revenue ($)")
    ax1.set_title("Total Revenue by Month")
    for i, v in enumerate(df['revenue']):
        ax1.text(i, v + 500, f"${v:,.0f}", ha='center', fontsize=9)

    # Bar chart: Avg fare
    ax2.bar(df['month_label'], df['avg_fare'], color='#27AE60', edgecolor='white')
    ax2.set_ylabel("Avg Fare ($)")
    ax2.set_title("Average Fare by Month")
    for i, v in enumerate(df['avg_fare']):
        ax2.text(i, v + 0.3, f"${v:.1f}", ha='center', fontsize=9)

    plt.tight_layout()
    st.pyplot(fig)

    st.dataframe(df[['month_label', 'trips', 'revenue', 'avg_fare']],
                column_config={
                    'month_label': 'Month',
                    'trips': 'Trips',
                    'revenue': 'Revenue ($)',
                    'avg_fare': 'Avg Fare ($)'
                }, hide_index=True)

# --- Section 4: Most Common Routes ---
elif selected == sections[3]:
    st.subheader("Most Common Routes (Pickup → Dropoff)")
    st.caption("Top routes by trip frequency. Shows where people travel most.")
    df = run_query("""
        SELECT
            pz.zone_name AS pickup,
            dz.zone_name AS dropoff,
            pz.borough AS pickup_boro,
            COUNT(*) AS trips,
            ROUND(AVG(t.total_amount), 2) AS avg_fare
        FROM yellow_taxi_2023 t
        JOIN taxi_zones pz ON t.pickup_zone = pz.zone_id
        JOIN taxi_zones dz ON t.dropoff_zone = dz.zone_id
        WHERE t.pickup_zone != t.dropoff_zone
        GROUP BY pz.zone_name, dz.zone_name, pz.borough
        HAVING COUNT(*) >= 3
        ORDER BY trips DESC
        LIMIT 15
    """)
    df['route'] = df['pickup'] + ' → ' + df['dropoff']
    st.dataframe(df[['route', 'trips', 'avg_fare']],
                column_config={
                    'route': 'Route',
                    'trips': 'Trips',
                    'avg_fare': 'Avg Fare ($)'
                }, hide_index=True)

    fig, ax = plt.subplots(figsize=(10, 6))
    display_routes = df['route'].str[:35][::-1]
    ax.barh(display_routes, df['trips'][::-1], color='#4A90D9')
    ax.set_xlabel("Trip Count")
    ax.set_title("Top 15 Routes")
    plt.tight_layout()
    st.pyplot(fig)

# --- Section 5: Fare per Mile ---
elif selected == sections[4]:
    st.subheader("Fare Rate by Trip Distance")
    st.caption("Shorter trips cost more per mile (base fare dominates). Longer trips get a better rate.")
    df = run_query("""
        SELECT
            CASE
                WHEN trip_distance < 1 THEN '0-1 mi'
                WHEN trip_distance < 3 THEN '1-3 mi'
                WHEN trip_distance < 5 THEN '3-5 mi'
                WHEN trip_distance < 10 THEN '5-10 mi'
                ELSE '10+ mi'
            END AS bucket,
            COUNT(*) AS trips,
            ROUND(AVG(fare_amount / NULLIF(trip_distance, 0)), 2) AS fare_per_mile,
            ROUND(AVG(total_amount), 2) AS avg_total
        FROM yellow_taxi_2023
        WHERE trip_distance > 0
        GROUP BY 1
        ORDER BY MIN(trip_distance)
    """)
    st.dataframe(df, column_config={
        'bucket': 'Distance',
        'trips': 'Trips',
        'fare_per_mile': 'Fare/Mile ($)',
        'avg_total': 'Avg Total ($)'
    }, hide_index=True)

    fig, ax = plt.subplots(figsize=(8, 5))
    colors = ['#E74C3C', '#F39C12', '#F1C40F', '#27AE60', '#4A90D9']
    ax.bar(df['bucket'], df['fare_per_mile'], color=colors[:len(df)])
    ax.set_ylabel("Fare per Mile ($)")
    ax.set_title("Fare Rate Decreases with Distance")
    for i, v in enumerate(df['fare_per_mile']):
        ax.text(i, v + 0.2, f"${v:.1f}/mi", ha='center', fontsize=10, fontweight='bold')
    plt.tight_layout()
    st.pyplot(fig)

    st.success(f"**Key insight:** A 0-1 mi trip costs ${df[df['bucket']=='0-1 mi']['fare_per_mile'].iloc[0]:.1f}/mile, while a 10+ mi trip costs only ${df[df['bucket']=='10+ mi']['fare_per_mile'].iloc[0]:.1f}/mile — a {((1 - df[df['bucket']=='10+ mi']['fare_per_mile'].iloc[0]/df[df['bucket']=='0-1 mi']['fare_per_mile'].iloc[0]))*100:.0f}% discount for longer trips.")

# --- Section 6: Longest Rides ---
elif selected == sections[5]:
    st.subheader("Longest Average Rides by Pickup Zone")
    st.caption("Where do taxis spend the most time on the road? (Traffic + distance)")
    df = run_query("""
        WITH durations AS (
            SELECT
                t.pickup_zone,
                EXTRACT(EPOCH FROM (t.dropoff_datetime - t.pickup_datetime)) / 60.0 AS dur_min,
                t.trip_distance
            FROM yellow_taxi_2023 t
            WHERE t.dropoff_datetime > t.pickup_datetime
        )
        SELECT
            z.zone_name,
            z.borough,
            COUNT(*) AS trips,
            ROUND(AVG(d.dur_min), 1) AS avg_min,
            ROUND(AVG(d.trip_distance), 2) AS avg_miles,
            ROUND(AVG(d.dur_min) / NULLIF(AVG(d.trip_distance), 0), 1) AS min_per_mile
        FROM durations d
        JOIN taxi_zones z ON d.pickup_zone = z.zone_id
        GROUP BY z.zone_name, z.borough
        HAVING COUNT(*) >= 10
        ORDER BY avg_min DESC
        LIMIT 10
    """)
    st.dataframe(df, column_config={
        'zone_name': 'Zone',
        'borough': 'Borough',
        'trips': 'Trips',
        'avg_min': 'Avg Duration (min)',
        'avg_miles': 'Avg Distance (mi)',
        'min_per_mile': 'Min/Mile'
    }, hide_index=True)

    fig, ax = plt.subplots(figsize=(9, 5))
    display = df['zone_name'].str[:22][::-1]
    colors = ['#E74C3C' if m > 10 else '#4A90D9' for m in df['min_per_mile'][::-1]]
    ax.barh(display, df['avg_min'][::-1], color=colors)
    ax.set_xlabel("Average Duration (min)")
    ax.set_title("Longest Rides (red = >10 min/mile, i.e. heavy traffic)")
    plt.tight_layout()
    st.pyplot(fig)

# --- Section 7: Outliers ---
elif selected == sections[6]:
    st.subheader("Outlier Trips (> Mean + 3σ)")
    st.caption("Statistically abnormal fares — potential data errors or extremely long/expensive trips.")
    df = run_query("""
        WITH stats AS (
            SELECT AVG(total_amount) AS mean_f, STDDEV(total_amount) AS std_f
            FROM yellow_taxi_2023
        )
        SELECT
            COUNT(*) AS outliers,
            ROUND(COUNT(*) * 100.0 / (SELECT COUNT(*) FROM yellow_taxi_2023), 2) AS pct,
            ROUND(MIN(t.total_amount), 2) AS min_fare,
            ROUND(MAX(t.total_amount), 2) AS max_fare,
            ROUND(AVG(t.total_amount), 2) AS avg_fare
        FROM yellow_taxi_2023 t, stats
        WHERE t.total_amount > stats.mean_f + 3 * stats.std_f
    """)
    c1, c2, c3 = st.columns(3)
    c1.metric("Outlier Trips", f"{df['outliers'].iloc[0]}")
    c2.metric("% of Total", f"{df['pct'].iloc[0]}%")
    c3.metric("Max Outlier Fare", f"${df['max_fare'].iloc[0]:,.0f}")

    # Distribution
    dist_df = run_query("SELECT total_amount FROM yellow_taxi_2023")
    stats_df = run_query("SELECT AVG(total_amount) AS m, STDDEV(total_amount) AS s FROM yellow_taxi_2023")
    threshold = stats_df['m'].iloc[0] + 3 * stats_df['s'].iloc[0]

    fig, ax = plt.subplots(figsize=(10, 5))
    clip_max = dist_df['total_amount'].quantile(0.95)
    ax.hist(dist_df['total_amount'].clip(upper=clip_max), bins=60, color='#4A90D9', alpha=0.7, edgecolor='white')
    ax.axvline(x=threshold, color='red', linewidth=2, linestyle='--', label=f'3σ threshold: ${threshold:.0f}')
    ax.axvline(x=stats_df['m'].iloc[0], color='green', linewidth=1.5, label=f'Mean: ${stats_df["m"].iloc[0]:.0f}')
    ax.set_xlabel("Total Fare ($)")
    ax.set_ylabel("Count")
    ax.set_title(f"Trip Cost Distribution ({df['outliers'].iloc[0]} outliers beyond 3σ)")
    ax.legend()
    plt.tight_layout()
    st.pyplot(fig)

# --- Section 8: Payment Methods ---
elif selected == sections[7]:
    st.subheader("Revenue by Payment Method")
    st.caption("How payment type affects fare and tipping. Note: Cash tips are often not separately recorded in TLC data.")

    df = run_query("""
        SELECT
            payment_type,
            COUNT(*) AS trips,
            ROUND(SUM(total_amount), 2) AS revenue,
            ROUND(SUM(total_amount) * 100.0 / SUM(SUM(total_amount)) OVER (), 1) AS pct,
            ROUND(AVG(total_amount), 2) AS avg_fare,
            ROUND(AVG(tip_amount), 2) AS avg_tip
        FROM yellow_taxi_2023
        GROUP BY payment_type
        ORDER BY revenue DESC
    """)
    df['payment_name'] = df['payment_type'].map(PAYMENT_MAP).fillna('Other')

    # Table (all rows)
    st.dataframe(df[['payment_name', 'trips', 'revenue', 'pct', 'avg_fare', 'avg_tip']],
                column_config={
                    'payment_name': 'Payment Method',
                    'trips': 'Trips',
                    'revenue': 'Revenue ($)',
                    'pct': '% of Revenue',
                    'avg_fare': 'Avg Fare ($)',
                    'avg_tip': 'Avg Tip ($)'
                }, hide_index=True)

    # Filter to only meaningful slices for the pie (>= 1% revenue)
    df_pie = df[df['pct'] >= 1.0].copy()

    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(12, 5))

    # Pie: Revenue share (only significant categories)
    colors = ['#4A90D9', '#27AE60', '#F39C12', '#E74C3C', '#9B59B6']
    wedges, texts, autotexts = ax1.pie(
        df_pie['revenue'],
        labels=df_pie['payment_name'],
        autopct='%1.1f%%',
        startangle=90,
        colors=colors[:len(df_pie)],
        textprops={'fontsize': 11}
    )
    ax1.set_title("Revenue Share (≥1% only)", fontsize=12)

    # Bar: Avg fare by payment method (more useful than tips here)
    df_bar = df[df['trips'] >= 5].copy()
    ax2.bar(df_bar['payment_name'], df_bar['avg_fare'], color='#4A90D9', edgecolor='white')
    ax2.set_ylabel("Avg Fare ($)")
    ax2.set_title("Average Fare by Payment Method")
    ax2.tick_params(axis='x', rotation=15)
    for i, v in enumerate(df_bar['avg_fare']):
        ax2.text(i, v + 0.3, f"${v:.1f}", ha='center', fontsize=10)

    plt.tight_layout()
    st.pyplot(fig)

    # Insight — honest framing
    credit = df[df['payment_name'] == 'Credit Card']
    cash = df[df['payment_name'] == 'Cash']
    if len(credit) > 0 and len(cash) > 0:
        st.info(
            f"**Key finding:** Credit card dominates at **{credit['pct'].iloc[0]:.0f}% of revenue** "
            f"({credit['trips'].iloc[0]} trips). Cash riders average ${cash['avg_fare'].iloc[0]} per ride. "
            f"Note: TLC data does not separately record tips for cash payments — the tip is included in the total fare."
        )   

# --- Footer ---
st.divider()
st.caption("Data: NYC Yellow Taxi 2023 (3,000 sample) | [GitHub](https://github.com/YOUR_USERNAME/nyc-taxi-analytics)")   
