# =====================================================================
# MinneMUDAC / The Food Group challenge
# QUESTION 4 - Food prices and food shelf activity   (ONE SELF-CONTAINED SCRIPT)
#
# What you need: R packages tidyverse, readxl, zoo, sandwich, lmtest, httr2
#                and these two files in the folder named by data_dir:
#                  org_FSStats.xlsx
#                  snap-dashboard-data-through-august-2026.xlsx
# Internet: only for the BLS API (prices + unemployment). If the API call fails the
#           script falls back to the Midwest CPI values embedded below.
# Outputs : tables in output/ and figures in output/figures/
# Run it top to bottom; every part prints what it did.
# Only data through July 2026 is used (the competition forbids August data of any kind).
# =====================================================================
library(tidyverse)   # dplyr, tidyr, ggplot2, readr, purrr, stringr
library(lubridate)   # dates
library(readxl)      # read .xlsx
library(zoo)  # na.approx(): fill gaps by interpolation
library(sandwich)    # Newey-West (HAC) standard errors
library(lmtest)      # coeftest()
library(splines) # ns(): smooth trend
library(tidycensus)
library(httr2)       # BLS API

# ---- settings you may change ----------------------------------------

data_dir <- "data"                                            # folder holding the two Excel files
FS_FILE  <- "org_FSStats.xlsx"
SNAP_FILE <- "snap-dashboard-data-through-august-2026.xlsx"
exclude_meal_programs <- TRUE      # meal programs serve prepared meals, not groceries; confirm with The Food Group
STABLE_MIN_MONTHS <- 50            # a "stable" site reports all 3 metrics in at least this many of the 55 months
MAXLAG  <- 18                      # longest price lag examined (months)
#census_api_key("cc18d7b465a086ce87d8664dfc9fe754a4616d5d", install = TRUE, overwrite = TRUE)
USE_API <- TRUE  # TRUE: BLS API (falls back automatically); FALSE: embedded Midwest CPI only
# For the API you can set a free key:  Sys.setenv(BLS_KEY = "your-key")  (optional)

dir.create("output/figures", recursive = TRUE, showWarnings = FALSE)
START <- as.Date("2022-01-01")
END   <- as.Date("2026-07-01")
save_fig <- function(p, name, w = 8, h = 5) ggsave(file.path("output/figures", name), p, width = w, height = h, dpi = 130)

# Simple replacement for janitor::clean_names(): "HouseholdsReg" -> "households_reg", "_id_site" -> "id_site"
clean_names <- function(df) {
  n <- names(df)
  n <- sub("^_+", "", n)
  n <- gsub("([a-z0-9])([A-Z])", "\\1_\\2", n)
  n <- gsub("([A-Z]+)([A-Z][a-z])", "\\1_\\2", n)
  names(df) <- tolower(gsub("[^A-Za-z0-9]+", "_", n))
  df
}

# =====================================================================
# PART A. LOAD AND CLEAN THE FOOD SHELF DATA (same rules as the Q1 script)
# One row = one site x one month. Visits = households (one visit = one household trip),
# individuals = adults + children + seniors, pounds = pounds distributed.
# =====================================================================
fs_raw <- read_excel(file.path(data_dir, FS_FILE)) |> clean_names()

fs <- fs_raw |>
  transmute(
    id_site, agency_type, food_bank,
    county_raw = county,
    # DateForSearch is the reliable period. A few 2023 rows carry month codes
    # 0 and 15; their DateForSearch resolves them to Dec 2022 and Mar 2024.
    date  = as.Date(date_for_search),
    year  = year(date),
    month = month(date),
    visits      = households_reg,
    individuals = individuals_reg,
    pounds      = pounds_reg,
    adults      = adults_reg,
    children    = children_reg,
    seniors     = seniors_reg
  )

# 1a. Standardise county names. The data splits Hennepin and Ramsey into
#     sub-areas and spells St. Louis two ways. Keep the sub-area for later.
fs <- fs |>
  mutate(
    subarea = if_else(str_detect(county_raw, "^(Hennepin|Ramsey)-"), county_raw, NA_character_),
    county  = case_when(
      str_detect(county_raw, "^Hennepin") ~ "Hennepin",
      str_detect(county_raw, "^Ramsey")   ~ "Ramsey",
      county_raw == "Saint Louis"         ~ "St. Louis",
      TRUE                                ~ county_raw
    )
  )

# 1b. ~130 rows have no county. Fill from the same site's other rows.
cat("Rows with missing county before fill:", sum(is.na(fs$county)), "\n")
fs <- fs |>
  group_by(id_site) |>
  mutate(county = coalesce(county, first(na.omit(county)))) |>
  ungroup()
cat("Rows with missing county after fill :", sum(is.na(fs$county)), "\n")

# 1c. Negative values are adjustments/errors -> treat as missing.
metric_cols <- c("visits", "individuals", "pounds", "adults", "children", "seniors")
fs <- fs |>
  mutate(across(all_of(metric_cols), ~ if_else(.x < 0, NA_real_, .x)))

# 1d. Obvious entry errors, e.g. one site-month with 273,385 visits but 646
#     individuals. Households can't exceed individuals, so flag and blank them.
#     (Starting rule - tune it, and tell The Food Group what you removed.)
fs <- fs |>
  mutate(suspect_visits = !is.na(visits) & !is.na(individuals) &
           visits > 1.5 * individuals & visits > 100)
cat("Suspect visit values blanked:", sum(fs$suspect_visits), "\n")
fs <- fs |> mutate(visits = if_else(suspect_visits, NA_real_, visits))

# 1e. Drop empty rows and exact duplicates. Rows that share a site-month but
#     have DIFFERENT numbers (e.g. site 1103 in 2024) look like two programs
#     under one site id, so we keep and sum them. Confirm with The Food Group.
fs <- fs |>
  filter(!(is.na(visits) & is.na(individuals) & is.na(pounds))) |>
  distinct(id_site, date, visits, individuals, pounds, .keep_all = TRUE)

n_multi <- fs |> count(id_site, date) |> filter(n > 1) |> nrow()
cat("Site-months still appearing more than once (kept, summed):", n_multi, "\n")

# 1f. Scope. Meal programs serve prepared meals, not food-shelf groceries.
#     Default: exclude them (confirm with The Food Group). Also hard-stop at
#     July 2026: the challenge forbids using August data for forecasting.
meal_types <- c("Meal Program", "Meal Programs", "On-Site Meal Programs")
exclude_meal_programs <- TRUE
if (exclude_meal_programs) fs <- fs |> filter(!(agency_type %in% meal_types))
fs <- fs |> filter(date <= as.Date("2026-07-01"))


# =====================================================================
# PART B. LOAD THE SNAP DATA (state total by month)
# Used only as a control for the end of the SNAP emergency allotments.
# All counties and tribal programs in the file are summed.
# =====================================================================
snap_state <- read_excel(file.path(data_dir, SNAP_FILE)) |>
  clean_names() |>
  transmute(date = as.Date(report_month), person_count, total_net) |>
  filter(date <= END) |>
  group_by(date) |>
  summarise(snap_persons = sum(person_count), snap_net = sum(total_net), .groups = "drop") |>
  arrange(date) |>
  mutate(bpp = snap_net / snap_persons)          # average benefit $ per SNAP person

# Embedded Midwest food-at-home CPI (BLS CUUR0200SAF11, via FRED), used if the API is unreachable.
# Oct 2025 is NA because BLS never collected it (federal shutdown).
cpi_fallback <- tribble(
  ~date, ~cpi_mw,
  "2019-01-01", 226.291,
  "2019-02-01", 228.347,
  "2019-03-01", 227.372,
  "2019-04-01", 226.719,
  "2019-05-01", 228.0,
  "2019-06-01", 227.95,
  "2019-07-01", 226.822,
  "2019-08-01", 227.101,
  "2019-09-01", 227.677,
  "2019-10-01", 227.603,
  "2019-11-01", 227.343,
  "2019-12-01", 227.074,
  "2020-01-01", 228.471,
  "2020-02-01", 229.829,
  "2020-03-01", 230.242,
  "2020-04-01", 236.431,
  "2020-05-01", 238.881,
  "2020-06-01", 238.991,
  "2020-07-01", 236.51,
  "2020-08-01", 234.738,
  "2020-09-01", 232.725,
  "2020-10-01", 234.245,
  "2020-11-01", 232.725,
  "2020-12-01", 233.262,
  "2021-01-01", 235.377,
  "2021-02-01", 235.863,
  "2021-03-01", 236.421,
  "2021-04-01", 237.832,
  "2021-05-01", 238.169,
  "2021-06-01", 239.911,
  "2021-07-01", 241.889,
  "2021-08-01", 243.148,
  "2021-09-01", 245.802,
  "2021-10-01", 249.139,
  "2021-11-01", 249.142,
  "2021-12-01", 250.622,
  "2022-01-01", 255.381,
  "2022-02-01", 258.599,
  "2022-03-01", 263.145,
  "2022-04-01", 267.001,
  "2022-05-01", 271.278,
  "2022-06-01", 274.159,
  "2022-07-01", 278.158,
  "2022-08-01", 280.226,
  "2022-09-01", 281.284,
  "2022-10-01", 282.059,
  "2022-11-01", 282.201,
  "2022-12-01", 283.1,
  "2023-01-01", 285.715,
  "2023-02-01", 286.503,
  "2023-03-01", 286.052,
  "2023-04-01", 286.499,
  "2023-05-01", 288.196,
  "2023-06-01", 287.256,
  "2023-07-01", 288.763,
  "2023-08-01", 288.105,
  "2023-09-01", 288.729,
  "2023-10-01", 288.13,
  "2023-11-01", 286.562,
  "2023-12-01", 287.002,
  "2024-01-01", 289.498,
  "2024-02-01", 289.635,
  "2024-03-01", 289.478,
  "2024-04-01", 289.107,
  "2024-05-01", 289.396,
  "2024-06-01", 289.56,
  "2024-07-01", 291.065,
  "2024-08-01", 290.118,
  "2024-09-01", 292.066,
  "2024-10-01", 292.313,
  "2024-11-01", 292.523,
  "2024-12-01", 291.229,
  "2025-01-01", 294.516,
  "2025-02-01", 293.462,
  "2025-03-01", 296.054,
  "2025-04-01", 294.13,
  "2025-05-01", 295.1,
  "2025-06-01", 297.298,
  "2025-07-01", 295.847,
  "2025-08-01", 298.807,
  "2025-09-01", 299.475,
  "2025-10-01", NA,
  "2025-11-01", 296.341,
  "2025-12-01", 296.429,
  "2026-01-01", 297.34,
  "2026-02-01", 301.197,
  "2026-03-01", 300.276,
  "2026-04-01", 302.196,
  "2026-05-01", 304.128,
  "2026-06-01", 302.643,
  "2026-07-01", 302.475
) |> mutate(date = as.Date(date), cpi_us = NA_real_, unemp_mn = NA_real_)

# ---------------------------------------------------------------------
# PART C / STEP 1. STATEWIDE MONTHLY FOOD SHELF ACTIVITY FROM A STABLE SET OF SITES
# ---------------------------------------------------------------------
site_m <- fs |>
  filter(date >= START, date <= END) |>
  group_by(id_site, date) |>
  summarise(across(c(visits, individuals, pounds, adults, children, seniors),
                   ~ if (all(is.na(.x))) NA_real_ else sum(.x, na.rm = TRUE)),
            .groups = "drop")

all_months <- seq(START, END, by = "month")
stable_ids <- site_m |>
  filter(!is.na(visits), !is.na(individuals), !is.na(pounds)) |>
  count(id_site) |> filter(n >= STABLE_MIN_MONTHS) |> pull(id_site)
cat("Sites in the raw panel:", n_distinct(site_m$id_site), "| stable sites:", length(stable_ids), "\n")

fill_gaps <- function(x) if (sum(!is.na(x)) < 2) x else na.approx(x, na.rm = FALSE, rule = 2)

state_m <- site_m |>
  filter(id_site %in% stable_ids) |>
  complete(id_site, date = all_months) |>
  arrange(id_site, date) |>
  group_by(id_site) |>
  mutate(across(c(visits, individuals, pounds, adults, children, seniors), fill_gaps)) |>
  ungroup() |>
  group_by(date) |>
  summarise(across(c(visits, individuals, pounds, adults, children, seniors), ~ sum(.x, na.rm = TRUE)),
            n_sites = n_distinct(id_site), .groups = "drop")

# Share of all activity captured by the stable sites (report this in the write-up)
cover <- site_m |> summarise(across(c(visits, individuals, pounds), ~ sum(.x[id_site %in% stable_ids], na.rm = TRUE) / sum(.x, na.rm = TRUE)))
print(cover)

# ---------------------------------------------------------------------
# STEP 2. PRICES AND CONTROLS
# ---------------------------------------------------------------------
get_bls <- function(ids, start_year = 2019, end_year = 2026) {
  body <- list(seriesid = as.list(ids), startyear = as.character(start_year), endyear = as.character(end_year))
  key <- Sys.getenv("BLS_KEY"); if (nzchar(key)) body$registrationkey <- key
  resp <- request("https://api.bls.gov/publicAPI/v2/timeseries/data/") |>
    req_body_json(body) |> req_perform() |> resp_body_json()
  if (!identical(resp$status, "REQUEST_SUCCEEDED")) stop("BLS API problem: ", paste(unlist(resp$message), collapse = " | "))
  map_dfr(resp$Results$series, function(s)
    map_dfr(s$data, ~ tibble(series = s$seriesID, year = as.integer(.x$year), period = .x$period,
                             value = suppressWarnings(as.numeric(.x$value))))) |>
    filter(str_detect(period, "^M(0[1-9]|1[0-2])$")) |>
    mutate(date = make_date(year, as.integer(str_sub(period, 2)), 1)) |>
    select(series, date, value)
}

macro <- NULL
if (USE_API) {
  macro <- tryCatch(
    get_bls(c("CUUR0000SAF11", "CUUR0200SAF11", "LASST270000000000003")) |>
      mutate(series = recode(series, CUUR0000SAF11 = "cpi_us", CUUR0200SAF11 = "cpi_mw",
                             LASST270000000000003 = "unemp_mn")) |>
      pivot_wider(names_from = series, values_from = value),
    error = function(e) { message("BLS API failed (", conditionMessage(e), "); using the embedded CPI values (no unemployment control)"); NULL })
}
if (is.null(macro)) {
  macro <- cpi_fallback
}
macro <- macro |> arrange(date) |> filter(date <= END)

# Compute everything that needs 2021 data BEFORE joining to the 2022+ activity series,
# otherwise the 12-month price changes for 2022 (the big price surge) are lost.
# October 2025 CPI was never collected (federal shutdown): interpolate
cat("Months with missing Midwest CPI:", format(macro$date[is.na(macro$cpi_mw)]), "\n")
macro <- macro |> mutate(cpi_mw = na.approx(cpi_mw, na.rm = FALSE))
if (!all(is.na(macro$cpi_us)))   macro <- macro |> mutate(cpi_us = na.approx(cpi_us, na.rm = FALSE))
have_unemp <- !all(is.na(macro$unemp_mn))
macro <- macro |>
  mutate(ln_cpi_mw   = log(cpi_mw),
         g_ln_cpi_mw = ln_cpi_mw - lag(ln_cpi_mw, 12),     # 12-month price growth
         infl_m      = ln_cpi_mw - lag(ln_cpi_mw, 1))      # 1-month price change
for (k in 0:MAXLAG) macro[[paste0("pg_l", k)]] <- dplyr::lag(macro$g_ln_cpi_mw, k)   # price growth k months earlier
if (!all(is.na(macro$cpi_us))) macro <- macro |> mutate(g_ln_cpi_us = log(cpi_us) - lag(log(cpi_us), 12))
if (have_unemp)                macro <- macro |> mutate(g_unemp = unemp_mn - lag(unemp_mn, 12))

# ---------------------------------------------------------------------
# STEP 3. SNAP CONTROL (emergency allotments ended spring 2023)
# ---------------------------------------------------------------------
snap_state <- snap_state |> mutate(g_ln_bpp = log(bpp) - lag(log(bpp), 12))
ea_date <- snap_state |> mutate(chg = bpp / lag(bpp) - 1) |>
  filter(date >= as.Date("2022-06-01"), date <= as.Date("2023-12-01")) |>
  slice_min(chg, n = 1) |> pull(date)
cat("Emergency-allotment drop found in report month:", format(ea_date), "\n")

# ---------------------------------------------------------------------
# STEP 4. ONE MONTHLY DATA FRAME
# ---------------------------------------------------------------------
yoy <- function(x) x - lag(x, 12)
d <- state_m |>
  left_join(macro, by = "date") |>
  left_join(snap_state, by = "date") |>
  arrange(date) |>
  mutate(
    t = row_number(), month = factor(month(date)),
    across(c(visits, individuals, pounds, children, adults, seniors), log, .names = "ln_{.col}"),
    # annual (12-month) change in each activity series (the first 12 months are lost)
    across(c(ln_visits, ln_individuals, ln_pounds, ln_children, ln_adults, ln_seniors), yoy,
           .names = "g_{.col}"),
    child_share = children / individuals,
    # a one-time LEVEL drop in SNAP benefits shows up as a 12-month plateau in 12-month changes
    ea_pulse = as.integer(date >= ea_date & date < ea_date %m+% months(12)))

outcomes <- c(Visits = "g_ln_visits", Individuals = "g_ln_individuals", Pounds = "g_ln_pounds")
ctrl <- c("ea_pulse", if (have_unemp) "g_unemp")   # controls in every price regression
cat("Controls used:", paste(ctrl, collapse = ", "), "\n")

# ---------------------------------------------------------------------
# STEP 5. LOOK FIRST
# ---------------------------------------------------------------------
p1 <- d |>
  transmute(date, Visits = visits, `Individuals served` = individuals, Pounds = pounds,
            `Midwest food-at-home CPI` = cpi_mw) |>
  pivot_longer(-date) |> group_by(name) |> mutate(index = 100 * value / first(value)) |>
  ggplot(aes(date, index, color = name)) + geom_line(linewidth = 0.9) +
  geom_vline(xintercept = ea_date, linetype = "dashed") +
  labs(title = "Food shelf activity (stable sites) and grocery prices", subtitle = "Jan 2022 = 100; dashed line = end of SNAP emergency allotments",
       x = NULL, y = "Index", color = NULL) + theme_minimal()
save_fig(p1, "q4_fig1_index.png")

p2 <- d |> filter(!is.na(g_ln_cpi_mw)) |>
  select(date, `Food-at-home CPI (Midwest)` = g_ln_cpi_mw, Visits = g_ln_visits,
         Individuals = g_ln_individuals, Pounds = g_ln_pounds) |>
  pivot_longer(-date) |>
  ggplot(aes(date, 100 * value, color = name)) + geom_hline(yintercept = 0, color = "grey60") +
  geom_line(linewidth = 0.9, na.rm = TRUE) +
  labs(title = "Year-over-year growth: grocery prices vs. food shelf activity", x = NULL, y = "% change from 12 months earlier", color = NULL) +
  theme_minimal()
save_fig(p2, "q4_fig2_yoy.png")

# ---------------------------------------------------------------------
# STEP 6. STATIONARITY (Phillips-Perron; H0 = unit root)
# ---------------------------------------------------------------------
pp_tbl <- d |> select(all_of(unname(outcomes)), g_ln_cpi_mw) |> drop_na() |>
  map_dfr(~ tibble(PP_stat = unname(PP.test(.x)$statistic), p_value = PP.test(.x)$p.value), .id = "series")
print(pp_tbl)
cat("Note: with ~43 growth observations these tests have little power. We use 12-month growth rates because\nraw levels trend (activity up, prices up), which would make any regression on levels spurious.\n")

# ---------------------------------------------------------------------
# STEP 7. TIMING
# Model A (main): for each lag k, regress 12-month growth in activity on 12-month growth
#   in the CPI k months earlier (+ controls). Common sample for every lag so the lag
#   profile compares like with like: months with a full 12 months of lags available.
# HAC (Newey-West) standard errors; we report bandwidth 6 AND 12.
# ---------------------------------------------------------------------
dd <- d |> mutate(row = row_number())
first_ok <- min(which(!is.na(dd$g_ln_visits) & !is.na(dd[[paste0("pg_l", MAXLAG)]])))
common <- dd |> slice(first_ok:n())
cat("Estimation sample (all lags):", format(min(common$date)), "to", format(max(common$date)), "n =", nrow(common), "\n")

lag_fit <- function(yvar, k, bw = 12, data = dd) {
  x <- data[[paste0("pg_l", k)]]
  dat <- data |> mutate(x = x, y = .data[[yvar]]) |> slice(first_ok:n()) |> drop_na(y, x, all_of(ctrl))
  f <- as.formula(paste("y ~ x +", paste(ctrl, collapse = " + ")))
  fit <- lm(f, data = dat)
  ct <- coeftest(fit, vcov = NeweyWest(fit, lag = bw, prewhite = FALSE))
  tibble(lag = k, n = nrow(dat), r_simple = cor(dat$y, dat$x), beta = ct["x", 1], se = ct["x", 2],
         p = ct["x", 4], lo = beta - 1.96 * se, hi = beta + 1.96 * se, bw = bw)
}
profile <- map_dfr(names(outcomes), function(nm)
  map_dfr(0:MAXLAG, ~ bind_rows(lag_fit(outcomes[[nm]], .x, 12), lag_fit(outcomes[[nm]], .x, 6)) |> mutate(metric = nm)))
write_csv(profile, "output/q4_lag_profile.csv")

best <- profile |> filter(bw == 12) |> group_by(metric) |> slice_max(abs(beta / se), n = 3) |> arrange(metric, desc(abs(beta / se)))
print(best, n = Inf)
cat("\nEffect size reading: beta = change in the 12-month % growth of activity for a 1-point rise in 12-month food-at-home inflation\n")
print(profile |> filter(bw == 12) |> select(metric, lag, n, r_simple, beta, se, p) |> mutate(across(where(is.numeric), ~ round(.x, 3))), n = Inf)

p3 <- profile |> filter(bw == 12) |>
  ggplot(aes(lag, beta)) + geom_hline(yintercept = 0, color = "grey50") +
  geom_ribbon(aes(ymin = lo, ymax = hi), alpha = 0.2) + geom_line() + geom_point() +
  facet_wrap(~ metric, ncol = 1, scales = "free_y") +
  scale_x_continuous(breaks = 0:MAXLAG) +
  labs(title = "Response of food shelf activity growth to grocery-price growth", subtitle = "By months since the price change; 95% Newey-West interval",
       x = "Months since the price change", y = "Coefficient") + theme_minimal()
save_fig(p3, "q4_fig3_lag_profile.png", h = 7)


# ---------------------------------------------------------------------
# STEP 7b. HONEST INFERENCE: a circular-shift permutation test
# Both series are smooth and trend-like, and there are only ~43 points, so ordinary
# p-values overstate certainty (two unrelated smooth curves often look "related").
# Test: slide the price series around in time (circular shifts) so any link with
# activity is broken but its smoothness is kept; recompute the whole lag profile
# each time; ask how often a SHIFTED price series produces a lag as strong as the
# one we observed (looking across all lags, so the search over lags is penalised).
# ---------------------------------------------------------------------
Pser   <- macro |> filter(!is.na(g_ln_cpi_mw)) |> select(date, g = g_ln_cpi_mw)
idx_t  <- match(common$date, Pser$date)
perm_test <- function(yvar) {
  y <- common[[yvar]]; Z <- common[ctrl]
  tstat <- function(P, k) {
    x <- P[idx_t - k]
    summary(lm(y ~ x + ., data = cbind(Z)))$coefficients["x", "t value"]
  }
  obs_t <- map_dbl(0:MAXLAG, ~ tstat(Pser$g, .x))
  N <- nrow(Pser)
  null_max <- map_dbl(1:(N - 1), function(s) {
    Ps <- Pser$g[((seq_len(N) - 1 + s) %% N) + 1]
    max(abs(map_dbl(0:MAXLAG, ~ tstat(Ps, .x))))
  })
  tibble(lag = 0:MAXLAG, t_obs = obs_t,
         p_lag_adj = map_dbl(0:MAXLAG, ~ mean(null_max >= abs(obs_t[.x + 1]))))   # adjusted for searching over lags
}
perm <- map_dfr(outcomes, perm_test, .id = "metric")
cat("\nPermutation (circular-shift) p-values, adjusted for searching over lags 0-", MAXLAG, ":\n", sep = "")
print(perm |> mutate(across(where(is.numeric), ~ round(.x, 3))) |> filter(lag %in% c(0, 3, 6, 9, 12, 15, 18)), n = Inf)
write_csv(perm, "output/q4_permutation.csv")

# ---------------------------------------------------------------------
# STEP 7c. THE STORY IN PLAIN NUMBERS (for donors and food shelves)
# ---------------------------------------------------------------------
story <- d |>
  mutate(period = case_when(date < as.Date("2023-01-01") ~ "2022", date < as.Date("2024-01-01") ~ "2023",
                            date < as.Date("2025-01-01") ~ "2024", date < as.Date("2026-01-01") ~ "2025", TRUE ~ "2026 (Jan-Jul)")) |>
  group_by(period) |>
  summarise(cpi_growth_pct = 100 * mean(g_ln_cpi_mw, na.rm = TRUE),
            across(c(visits, individuals, pounds), ~ mean(.x), .names = "avg_monthly_{.col}"), .groups = "drop") |>
  mutate(across(starts_with("avg_monthly"), ~ round(.x / lag(.x) * 100 - 100, 1), .names = "chg_{.col}")) 
cat("\nYear-by-year summary (price growth = average 12-month food-at-home inflation, Midwest):\n"); print(story, width = Inf)
write_csv(story, "output/q4_story_table.csv")

peaks <- tibble(
  series = c("Food-at-home CPI growth (12-mo)", names(outcomes)),
  peak_month = c(format(macro$date[which.max(ifelse(macro$date >= START, macro$g_ln_cpi_mw, NA))]),
                 map_chr(outcomes, ~ format(d$date[which.max(d[[.x]])]))),
  peak_value_pct = c(100 * max(macro$g_ln_cpi_mw[macro$date >= START], na.rm = TRUE), map_dbl(outcomes, ~ 100 * max(d[[.x]], na.rm = TRUE))))
cat("\nWhen did each series' 12-month growth peak?\n"); print(peaks)
write_csv(peaks, "output/q4_peaks.csv")

# ---------------------------------------------------------------------
# STEP 8. ROBUSTNESS (Model B: monthly changes, seasonality handled with month dummies)
#   dlog(activity_t) on monthly inflation at lags 0..6 (separately), month dummies, EA dummy
# ---------------------------------------------------------------------
dB <- d |> mutate(dv = ln_visits - lag(ln_visits), di = ln_individuals - lag(ln_individuals), dp = ln_pounds - lag(ln_pounds),
                  ea = as.integer(date == ea_date))
modB <- function(yv, k) {
  dat <- dB |> mutate(x = lag(infl_m, k), y = .data[[yv]]) |> drop_na(y, x)
  fit <- lm(y ~ x + month + ea, data = dat)
  ct <- coeftest(fit, vcov = NeweyWest(fit, lag = 3, prewhite = FALSE))
  tibble(lag = k, n = nrow(dat), beta = ct["x", 1], se = ct["x", 2], p = ct["x", 4])
}
robB <- map_dfr(c(Visits = "dv", Individuals = "di", Pounds = "dp"), function(yv) map_dfr(0:6, ~ modB(yv, .x)), .id = "metric")
cat("\nRobustness model B (monthly change on monthly inflation):\n"); print(robB |> mutate(across(where(is.numeric), ~ round(.x, 3))), n = Inf)
write_csv(robB, "output/q4_robustness_monthly.csv")

# ---------------------------------------------------------------------
# STEP 9. WHO RESPONDS: children / adults / seniors
# ---------------------------------------------------------------------
who_out <- c(Children = "g_ln_children", Adults = "g_ln_adults", Seniors = "g_ln_seniors")
who <- map_dfr(names(who_out), function(nm) map_dfr(0:MAXLAG, ~ lag_fit(who_out[[nm]], .x, 12) |> mutate(metric = nm)))
write_csv(who, "output/q4_who_profile.csv")
print(who |> select(metric, lag, beta, se, p) |> mutate(across(where(is.numeric), ~ round(.x, 3))) |> filter(lag %in% c(0, 3, 6, 9, 12)), n = Inf)

# ---------------------------------------------------------------------
# STEP 10. OTHER CYCLICAL PATTERNS
# (a) STL decomposition of log activity
# (b) Size of the seasonal swing vs. what prices could explain (CPI seasonal swing)
# (c) F-test: do month-of-year effects matter after removing a smooth trend?
# (d) Periodogram of the detrended series: which cycle lengths dominate?
# ---------------------------------------------------------------------
mk_ts <- function(x) ts(x, start = c(2022, 1), frequency = 12)
stl_out <- map_dfr(c(Visits = "ln_visits", Individuals = "ln_individuals", Pounds = "ln_pounds", `CPI (Midwest)` = "ln_cpi_mw"), function(v) {
  s <- stl(mk_ts(d[[v]]), s.window = "periodic", robust = TRUE)
  tibble(date = d$date, seasonal = as.numeric(s$time.series[, "seasonal"]), trend = as.numeric(s$time.series[, "trend"]), remainder = as.numeric(s$time.series[, "remainder"]))
}, .id = "series")
season_prof <- stl_out |> mutate(m = month(date, label = TRUE)) |> group_by(series, m) |> summarise(seasonal = mean(seasonal), .groups = "drop")
swing <- season_prof |> group_by(series) |> summarise(peak = m[which.max(seasonal)], trough = m[which.min(seasonal)],
                                                      swing_pct = 100 * (exp(max(seasonal) - min(seasonal)) - 1), .groups = "drop")
cat("\nSeasonal swing (trough to peak, % of level):\n"); print(swing)
write_csv(season_prof, "output/q4_seasonal_profile.csv")

p4 <- season_prof |> ggplot(aes(m, 100 * seasonal, group = series, color = series)) +
  geom_hline(yintercept = 0, color = "grey60") + geom_line(linewidth = 0.9) + geom_point() +
  labs(title = "Typical seasonal pattern by month", subtitle = "STL seasonal component, % above/below trend", x = NULL, y = "%", color = NULL) + theme_minimal()
save_fig(p4, "q4_fig4_seasonal.png")

# (c) F-test of month effects after a smooth trend (natural spline, 4 df)
ftests <- map_dfr(c(Visits = "ln_visits", Individuals = "ln_individuals", Pounds = "ln_pounds", `Children share` = "child_share"), function(v) {
  dat <- d |> mutate(y = .data[[v]])
  a <- lm(y ~ ns(t, df = 4), data = dat); b <- lm(y ~ ns(t, df = 4) + month, data = dat)
  an <- anova(a, b); tibble(F = an$F[2], p = an$`Pr(>F)`[2], r2_trend = summary(a)$r.squared, r2_trend_month = summary(b)$r.squared)
}, .id = "series")
cat("\nF-test: month-of-year effects after smooth trend\n"); print(ftests)

# children share seasonal pattern (school-year signal)
cs <- d |> mutate(m = month(date, label = TRUE)) |> group_by(m) |> summarise(child_share = mean(child_share), .groups = "drop")
print(cs)
p5 <- ggplot(cs, aes(m, 100 * child_share, group = 1)) + geom_line() + geom_point() +
  labs(title = "Children as a share of individuals served, by month", x = NULL, y = "%") + theme_minimal()
save_fig(p5, "q4_fig5_child_share.png")

# (d) Periodogram of the detrended log activity (period in months)
per <- map_dfr(c(Visits = "ln_visits", Individuals = "ln_individuals", Pounds = "ln_pounds"), function(v) {
  r <- resid(lm(d[[v]] ~ ns(d$t, df = 4)))
  sp <- spec.pgram(mk_ts(r), taper = 0.1, plot = FALSE)
  tibble(period_months = 12 / sp$freq, power = sp$spec)
}, .id = "series")
print(per |> group_by(series) |> slice_max(power, n = 3) |> arrange(series, desc(power)))

# (e) What is left after seasonality AND prices? STL remainder vs shock dates
rem <- stl_out |> filter(series %in% c("Visits", "Individuals", "Pounds")) |> select(date, series, remainder)
p6 <- ggplot(rem, aes(date, 100 * remainder, color = series)) + geom_hline(yintercept = 0, color = "grey60") + geom_line() +
  geom_vline(xintercept = c(ea_date, as.Date("2025-10-01")), linetype = "dashed") +
  labs(title = "What is left after trend and seasonality (STL remainder)", subtitle = "Dashed: SNAP emergency allotments end; federal shutdown (Oct 2025)",
       x = NULL, y = "% deviation", color = NULL) + theme_minimal()
save_fig(p6, "q4_fig6_remainder.png")
write_csv(stl_out, "output/q4_stl.csv")
cat("\nDone.\n")

