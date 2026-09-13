-- Calendar grid is complete before ROWS windows are applied.
-- End-of-day T includes the observation on T; all predictors end at or before T.
WITH windows AS (
    SELECT *, date AS origin,
        date + INTERVAL 7 DAY AS target_end,
        count(contract_hours) OVER hist28 AS history_count,
        sum(contract_hours) OVER hist7 AS previous_7,
        avg(contract_hours) OVER hist28 * 7 AS trailing_28,
        stddev_pop(contract_hours) OVER hist7 AS contract_std7,
        stddev_pop(contract_hours) OVER hist28 AS contract_std28,
        avg(CASE WHEN contract_hours = 0 THEN 1.0 WHEN contract_hours IS NULL THEN NULL ELSE 0.0 END) OVER hist28 AS zero_fraction28,
        lag(contract_hours, 7) OVER facility_dates AS contract_lag7,
        lag(contract_hours, 14) OVER facility_dates AS contract_lag14,
        avg(employee_hours) OVER hist7 AS employee_mean7,
        avg(employee_hours) OVER hist28 AS employee_mean28,
        avg(census) OVER hist7 AS census_mean7,
        lag(census, 7) OVER facility_dates AS census_lag7,
        count(contract_hours) OVER future7 AS target_count,
        sum(contract_hours) OVER future7 AS target_sum,
        extract(dow FROM date + INTERVAL 1 DAY) AS next_weekday,
        sin(2*pi()*extract(doy FROM date + INTERVAL 1 DAY)/365.25) AS season_sin,
        cos(2*pi()*extract(doy FROM date + INTERVAL 1 DAY)/365.25) AS season_cos
    FROM daily
    WINDOW facility_dates AS (PARTITION BY facility ORDER BY date),
        hist7 AS (PARTITION BY facility ORDER BY date ROWS BETWEEN 6 PRECEDING AND CURRENT ROW),
        hist28 AS (PARTITION BY facility ORDER BY date ROWS BETWEEN 27 PRECEDING AND CURRENT ROW),
        future7 AS (PARTITION BY facility ORDER BY date ROWS BETWEEN 1 FOLLOWING AND 7 FOLLOWING)
)
SELECT facility, name, county, state, volume_group, origin, target_end,
       contract_hours AS contract_today, previous_7, trailing_28, contract_std7, contract_std28,
       zero_fraction28, contract_lag7, contract_lag14, employee_mean7, employee_mean28,
       census AS census_today, census_mean7, census_lag7, next_weekday, season_sin, season_cos,
       history_count, history_count = 28 AS eligible,
       CASE WHEN target_count = 7 THEN target_sum ELSE NULL END AS target
FROM windows
