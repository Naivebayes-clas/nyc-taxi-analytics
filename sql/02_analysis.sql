-- ============================================================
-- NYC Yellow Taxi Analytics — Advanced SQL Queries
-- Dataset: yellow_taxi_2023 (~3000 rows, Jan/May/Nov 2023)
-- ============================================================

-- QUERY 1: Average fare by hour and day of week
-- Concept: EXTRACT(), GROUP BY, ORDER BY
-- Business question: "When should a driver be on the road to maximize earnings?"

SELECT
    EXTRACT(DOW FROM pickup_datetime) AS day_of_week,
    EXTRACT(HOUR FROM pickup_datetime) AS hour,
    COUNT(*) AS trip_count,
    ROUND(AVG(fare_amount), 2) AS avg_fare,
    ROUND(AVG(total_amount), 2) AS avg_total,
    ROUND(AVG(trip_distance), 2) AS avg_distance
FROM yellow_taxi_2023
GROUP BY day_of_week, hour
ORDER BY day_of_week, hour;


-- QUERY 2: Top 10 pickup zones by trip volume
-- Concept: RANK() window function + JOIN for zone names
-- Business question: "Where are the busiest pickup spots?"

WITH zone_counts AS (
    SELECT
        z.zone_name,
        z.borough,
        COUNT(*) AS trip_count,
        ROUND(AVG(t.fare_amount), 2) AS avg_fare,
        RANK() OVER (ORDER BY COUNT(*) DESC) AS pickup_rank
    FROM yellow_taxi_2023 t
    JOIN taxi_zones z ON t.pickup_zone = z.zone_id
    GROUP BY z.zone_name, z.borough
)
SELECT
    pickup_rank,
    zone_name,
    borough,
    trip_count,
    avg_fare
FROM zone_counts
WHERE pickup_rank <= 10
ORDER BY pickup_rank;


-- QUERY 3: Monthly revenue trend with month-over-month growth
-- Concept: LAG() window function, date_trunc
-- Business question: "Is the taxi business growing or shrinking?"

WITH monthly_revenue AS (
    SELECT
        date_trunc('month', pickup_datetime) AS month,
        COUNT(*) AS trips,
        SUM(total_amount) AS revenue,
        ROUND(AVG(total_amount), 2) AS avg_fare
    FROM yellow_taxi_2023
    GROUP BY date_trunc('month', pickup_datetime)
)
SELECT
    month,
    trips,
    ROUND(revenue, 2) AS revenue,
    avg_fare,
    LAG(revenue) OVER (ORDER BY month) AS prev_month_revenue,
    ROUND(
        (revenue - LAG(revenue) OVER (ORDER BY month))
        / LAG(revenue) OVER (ORDER BY month) * 100, 2
    ) AS mom_growth_pct
FROM monthly_revenue
ORDER BY month;


-- QUERY 4: Most common routes (pickup zone → dropoff zone)
-- Concept: Multi-column GROUP BY + HAVING + JOIN for zone names
-- Business question: "What are the most popular trips?"

SELECT
    pz.zone_name AS pickup_zone_name,
    dz.zone_name AS dropoff_zone_name,
    pz.borough AS pickup_borough,
    dz.borough AS dropoff_borough,
    COUNT(*) AS trip_count,
    ROUND(AVG(t.trip_distance), 2) AS avg_distance,
    ROUND(AVG(t.total_amount), 2) AS avg_fare,
    ROUND(MIN(t.total_amount), 2) AS min_fare,
    ROUND(MAX(t.total_amount), 2) AS max_fare
FROM yellow_taxi_2023 t
JOIN taxi_zones pz ON t.pickup_zone = pz.zone_id
JOIN taxi_zones dz ON t.dropoff_zone = dz.zone_id
WHERE t.pickup_zone != t.dropoff_zone
GROUP BY pz.zone_name, dz.zone_name, pz.borough, dz.borough
HAVING COUNT(*) >= 3
ORDER BY trip_count DESC
LIMIT 20;


-- QUERY 5: Fare per mile by distance bucket
-- Concept: CASE WHEN for bucketing, PERCENTILE_CONT with numeric cast
-- Business question: "Do longer trips get a better rate per mile?"

WITH bucketed AS (
    SELECT
        CASE
            WHEN trip_distance < 1 THEN '0-1 mi'
            WHEN trip_distance < 3 THEN '1-3 mi'
            WHEN trip_distance < 5 THEN '3-5 mi'
            WHEN trip_distance < 10 THEN '5-10 mi'
            ELSE '10+ mi'
        END AS distance_bucket,
        trip_distance,
        fare_amount,
        total_amount
    FROM yellow_taxi_2023
    WHERE trip_distance > 0
)
SELECT
    distance_bucket,
    COUNT(*) AS trips,
    ROUND(AVG(trip_distance), 2) AS avg_distance,
    ROUND(AVG(fare_amount), 2) AS avg_fare,
    ROUND(AVG(fare_amount / NULLIF(trip_distance, 0)), 2) AS fare_per_mile,
    ROUND(PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY total_amount)::numeric, 2) AS median_total
FROM bucketed
GROUP BY distance_bucket
ORDER BY MIN(trip_distance);


-- QUERY 6: Average ride duration by pickup zone (top 10 longest)
-- Concept: EXTRACT(EPOCH FROM interval), RANK() + JOIN for zone names
-- Business question: "Where do rides take the longest?"

WITH durations AS (
    SELECT
        t.pickup_zone,
        EXTRACT(EPOCH FROM (t.dropoff_datetime - t.pickup_datetime)) / 60.0 AS duration_min,
        t.trip_distance
    FROM yellow_taxi_2023 t
    WHERE t.dropoff_datetime > t.pickup_datetime
)
SELECT
    z.zone_name,
    z.borough,
    COUNT(*) AS trips,
    ROUND(AVG(d.duration_min), 1) AS avg_duration_min,
    ROUND(AVG(d.trip_distance), 2) AS avg_distance,
    ROUND(AVG(d.duration_min) / NULLIF(AVG(d.trip_distance), 0), 1) AS min_per_mile,
    RANK() OVER (ORDER BY AVG(d.duration_min) DESC) AS slowest_rank
FROM durations d
JOIN taxi_zones z ON d.pickup_zone = z.zone_id
GROUP BY z.zone_name, z.borough
HAVING COUNT(*) >= 10
ORDER BY avg_duration_min DESC
LIMIT 10;


-- QUERY 7: Outlier detection — trips with total > mean + 3*stddev
-- Concept: Subquery for stats, filtering by threshold
-- Business question: "How many trips are abnormally expensive?"

WITH stats AS (
    SELECT
        AVG(total_amount) AS mean_fare,
        STDDEV(total_amount) AS std_fare
    FROM yellow_taxi_2023
)
SELECT
    COUNT(*) AS outlier_count,
    ROUND(COUNT(*) * 100.0 / (SELECT COUNT(*) FROM yellow_taxi_2023), 2) AS pct_of_total,
    ROUND(MIN(t.total_amount), 2) AS min_outlier_fare,
    ROUND(MAX(t.total_amount), 2) AS max_outlier_fare,
    ROUND(AVG(t.total_amount), 2) AS avg_outlier_fare
FROM yellow_taxi_2023 t, stats
WHERE t.total_amount > stats.mean_fare + 3 * stats.std_fare;


-- QUERY 8: Revenue by payment method (pivoted style)
-- Concept: CTEs + conditional aggregation + window function for percentage
-- Business question: "How does payment method affect revenue?"

WITH payment_breakdown AS (
    SELECT
        payment_type,
        COUNT(*) AS trips,
        SUM(total_amount) AS revenue,
        ROUND(AVG(total_amount), 2) AS avg_fare,
        ROUND(SUM(tip_amount), 2) AS total_tips,
        ROUND(AVG(tip_amount), 2) AS avg_tip
    FROM yellow_taxi_2023
    GROUP BY payment_type
)
SELECT
    payment_type,
    trips,
    ROUND(revenue, 2) AS revenue,
    ROUND(revenue * 100.0 / SUM(revenue) OVER (), 1) AS revenue_pct,
    avg_fare,
    total_tips,
    avg_tip,
    ROUND(avg_tip * 100.0 / NULLIF(avg_fare, 0), 1) AS tip_pct_of_fare
FROM payment_breakdown
ORDER BY revenue DESC; 
