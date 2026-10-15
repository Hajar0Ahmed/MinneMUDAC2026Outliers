Question 5: SNAP and Food Shelf Use
================

``` r
library(readxl)
library(dplyr)
```

    ## Warning: package 'dplyr' was built under R version 4.5.2

    ## 
    ## Attaching package: 'dplyr'

    ## The following objects are masked from 'package:stats':
    ## 
    ##     filter, lag

    ## The following objects are masked from 'package:base':
    ## 
    ##     intersect, setdiff, setequal, union

``` r
fs <- read_excel("data/org_FSStats.xlsx", guess_max = 30000)

food_shelf_types <- c("Brick and Mortar Site", "Brick and Mortar Sites", "Food Shelf",
                      "Mobile", "Outreach Program", "Tribal Program", "College Campus Program")

fs_month <- fs |>
  mutate(date = as.Date(DateForSearch)) |>
  filter(date <= as.Date("2026-07-01"),          # competition rule: no August 2026
         AgencyType %in% food_shelf_types) |>
  select(site        = `_id_site`,
         date,
         county      = County,
         visits      = HouseholdsReg,
         pounds      = PoundsReg,
         individuals = IndividualsReg) |>
  distinct() |>
  mutate(visits = ifelse(visits > 3 * individuals, NA, visits),
         pounds = ifelse(pounds < 0, NA, pounds),
         county = case_when(
           county %in% c("Hennepin-Minneapolis", "Hennepin-Suburbs") ~ "Hennepin",
           county %in% c("Ramsey-Saint Paul", "Ramsey-Suburbs")      ~ "Ramsey",
           county == "Saint Louis"   ~ "St. Louis",
           county == "Lac Qui Parle" ~ "Lac qui Parle",
           TRUE ~ county)) |>
  filter(!is.na(county))

state_month <- fs_month |>
  group_by(date) |>
  summarise(visits      = sum(visits, na.rm = TRUE),
            pounds      = sum(pounds, na.rm = TRUE),
            individuals = sum(individuals, na.rm = TRUE),
            n_sites     = n_distinct(site))

range(fs_month$date)
```

    ## [1] "2022-01-01" "2026-07-01"

``` r
nrow(state_month)
```

    ## [1] 55

``` r
head(state_month)
```

    ## # A tibble: 6 × 5
    ##   date       visits    pounds individuals n_sites
    ##   <date>      <dbl>     <dbl>       <dbl>   <int>
    ## 1 2022-01-01 121270  8650033.      355540     426
    ## 2 2022-02-01 160959  7544640.      341486     412
    ## 3 2022-03-01 145037  9307557.      432935     431
    ## 4 2022-04-01 149021  9638960.      472104     415
    ## 5 2022-05-01 149773  9915605.      481499     426
    ## 6 2022-06-01 176440 10227563.      505196     432

``` r
tail(state_month)
```

    ## # A tibble: 6 × 5
    ##   date       visits    pounds individuals n_sites
    ##   <date>      <dbl>     <dbl>       <dbl>   <int>
    ## 1 2026-02-01 267284 13304129.      852754     457
    ## 2 2026-03-01 277840 13591603.      862114     459
    ## 3 2026-04-01 263067 13067724.      801232     456
    ## 4 2026-05-01 229370 11536292.      710185     452
    ## 5 2026-06-01 239937 12253807.      740478     448
    ## 6 2026-07-01 239143 12999407.      739103     449

``` r
# install.packages("pdftools")   # only needed once
library(pdftools)
```

    ## Warning: package 'pdftools' was built under R version 4.5.3

    ## Using poppler version 26.01.0

``` r
library(stringr)
library(readr)
```

    ## Warning: package 'readr' was built under R version 4.5.3

``` r
month_pattern <- "(\\d{4})\\s+(January|February|March|April|May|June|July|August|September|October|November|December)"
row_pattern   <- "^\\s*(\\d{1,3}|TOTAL)\\s+(.*?)\\s*([\\d,]+)\\s+([\\d,]+)\\s+([\\d,.]+)\\s*$"

read_snap_pdf <- function(file) {
  pages <- pdf_text(file)
  rows <- list()
  current_month <- as.Date(NA)
  for (page in pages) {
    m <- str_match(page, month_pattern)
    if (!is.na(m[1])) current_month <- as.Date(paste(m[2], match(m[3], month.name), 1, sep = "-"))
    lines <- str_split(page, "\n")[[1]]
    hit <- str_match(lines, row_pattern)
    hit <- hit[!is.na(hit[, 1]), , drop = FALSE]
    if (nrow(hit) > 0) {
      rows[[length(rows) + 1]] <- tibble(
        file    = basename(file),
        date    = current_month,
        code    = hit[, 2],
        name    = str_squish(hit[, 3]),
        cases   = parse_number(hit[, 4]),
        people  = parse_number(hit[, 5]),
        dollars = parse_number(hit[, 6]))
    }
  }
  bind_rows(rows)
}

snap_files <- list.files("data/SNAP", pattern = "\\.pdf$", full.names = TRUE)
snap_raw   <- bind_rows(lapply(snap_files, read_snap_pdf))

# COMPETITION RULE: drop anything after July 2026
snap_raw <- snap_raw |> filter(date <= as.Date("2026-07-01"))

snap_raw |>
  group_by(file) |>
  summarise(first_month = min(date), last_month = max(date), months = n_distinct(date))
```

    ## # A tibble: 5 × 4
    ##   file          first_month last_month months
    ##   <chr>         <date>      <date>      <int>
    ## 1 SNAP 2022.pdf 2022-01-01  2022-12-01     12
    ## 2 SNAP 2023.pdf 2023-01-01  2023-12-01     12
    ## 3 SNAP 2024.pdf 2024-01-01  2024-12-01     12
    ## 4 SNAP 2025.pdf 2025-01-01  2025-12-01     12
    ## 5 SNAP 2026.pdf 2026-01-01  2026-07-01      7

``` r
# 1. Check: do the county rows add up to the TOTAL row? (within 5 people)
snap_raw |>
  group_by(date) |>
  summarise(sum_of_rows = sum(people[code != "TOTAL"]),
            total_row   = sum(people[code == "TOTAL"])) |>
  mutate(match = abs(total_row - sum_of_rows) <= 5) |>
  count(match)
```

    ## # A tibble: 1 × 2
    ##   match     n
    ##   <lgl> <int>
    ## 1 TRUE     55

``` r
# 2. Statewide SNAP by month (from the TOTAL row; drop empty, not-yet-published months)
snap_state <- snap_raw |>
  filter(code == "TOTAL") |>
  group_by(date) |>
  summarise(snap_people  = sum(people),
            snap_dollars = sum(dollars)) |>
  filter(snap_people > 0) |>
  mutate(dollars_per_person = snap_dollars / snap_people)

# 3. County SNAP by month (counties 1-87 only; tribal nations dropped)
snap_county <- snap_raw |>
  filter(code != "TOTAL") |>
  mutate(code = as.numeric(code)) |>
  filter(code <= 87, people > 0) |>
  mutate(fips = sprintf("27%03d", 2 * code - 1)) |>
  select(fips, name, date, cases, people, dollars)

range(snap_state$date)   # should end 2026-03-01
```

    ## [1] "2022-01-01" "2026-03-01"

``` r
head(snap_state)
```

    ## # A tibble: 6 × 4
    ##   date       snap_people snap_dollars dollars_per_person
    ##   <date>           <dbl>        <dbl>              <dbl>
    ## 1 2022-01-01      425042    96306389                227.
    ## 2 2022-02-01      429062   100243903.               234.
    ## 3 2022-03-01      435272   100659469.               231.
    ## 4 2022-04-01      434344    99911780.               230.
    ## 5 2022-05-01      434187   100475465.               231.
    ## 6 2022-06-01      436081    99848163                229.

``` r
library(tidyr)
```

    ## Warning: package 'tidyr' was built under R version 4.5.2

``` r
library(ggplot2)
```

    ## Warning: package 'ggplot2' was built under R version 4.5.3

``` r
dir.create("output", showWarnings = FALSE)

q5_state <- state_month |>
  left_join(snap_state, by = "date")

before_after <- q5_state |>
  filter(date >= as.Date("2022-03-01"), date <= as.Date("2024-02-01")) |>
  mutate(period = ifelse(date < as.Date("2023-03-01"),
                         "Before\n(Mar 2022 - Feb 2023)",
                         "After\n(Mar 2023 - Feb 2024)")) |>
  group_by(period) |>
  summarise(`Food shelf visits per month`       = mean(visits),
            `SNAP dollars per person per month` = mean(dollars_per_person))

before_after
```

    ## # A tibble: 2 × 3
    ##   period                          Food shelf visits per…¹ SNAP dollars per per…²
    ##   <chr>                                             <dbl>                  <dbl>
    ## 1 "After\n(Mar 2023 - Feb 2024)"                  217064.                   169.
    ## 2 "Before\n(Mar 2022 - Feb 2023)"                 166953.                   238.
    ## # ℹ abbreviated names: ¹​`Food shelf visits per month`,
    ## #   ²​`SNAP dollars per person per month`

``` r
before_after |>
  pivot_longer(-period, names_to = "measure", values_to = "value") |>
  mutate(period = factor(period, levels = c("Before\n(Mar 2022 - Feb 2023)",
                                            "After\n(Mar 2023 - Feb 2024)"))) |>
  ggplot(aes(x = period, y = value, fill = period)) +
  geom_col(width = 0.6) +
  geom_text(aes(label = scales::comma(round(value))), vjust = -0.4, size = 4) +
  facet_wrap(~ measure, scales = "free_y") +
  scale_fill_manual(values = c("grey60", "steelblue")) +
  scale_y_continuous(labels = scales::comma, expand = expansion(mult = c(0, 0.12))) +
  labs(x = NULL, y = NULL,
       title = "When extra SNAP payments ended, food shelf visits rose",
       subtitle = "Monthly averages, 12 months before vs. 12 months after March 2023",
       caption = "Sources: The Food Group; MN DHS SNAP and State-Funded Food reports") +
  theme_minimal() +
  theme(legend.position = "none")
```

![](Ewura-Work-5_files/figure-gfm/unnamed-chunk-4-1.png)<!-- -->

``` r
ggsave("output/q5_chart1_before_after.png", width = 8, height = 5, bg = "white")
```

``` r
library(lubridate)
```

    ## Warning: package 'lubridate' was built under R version 4.5.2

    ## 
    ## Attaching package: 'lubridate'

    ## The following objects are masked from 'package:base':
    ## 
    ##     date, intersect, setdiff, union

``` r
# % change: months after a SNAP change vs the same months one year earlier
compare_years <- function(data, start, end) {
  after  <- data |> filter(date >= as.Date(start), date <= as.Date(end))
  before <- data |> filter(date >= as.Date(start) - years(1), date <= as.Date(end) - years(1))
  tibble(visits_change      = 100 * (sum(after$visits) / sum(before$visits) - 1),
         pounds_change      = 100 * (sum(after$pounds) / sum(before$pounds) - 1),
         individuals_change = 100 * (sum(after$individuals) / sum(before$individuals) - 1))
}

snap_events <- bind_rows(
  compare_years(q5_state, "2023-03-01", "2024-02-01") |> mutate(period = "12 months AFTER the Mar 2023 cut"),
  compare_years(q5_state, "2025-05-01", "2025-10-01") |> mutate(period = "6 months BEFORE Nov 2025"),
  compare_years(q5_state, "2025-11-01", "2026-02-01") |> mutate(period = "4 months AFTER Nov 2025"),
  compare_years(q5_state, "2026-03-01", "2026-07-01") |> mutate(period = "5 months AFTER Mar 2026")) |>
  select(period, everything()) |>
  mutate(across(where(is.numeric), ~ round(.x, 1)))

snap_events
```

    ## # A tibble: 4 × 4
    ##   period                          visits_change pounds_change individuals_change
    ##   <chr>                                   <dbl>         <dbl>              <dbl>
    ## 1 12 months AFTER the Mar 2023 c…          30            18.4               35.9
    ## 2 6 months BEFORE Nov 2025                  6.5          -3.5                1  
    ## 3 4 months AFTER Nov 2025                   4.6           1.7                4  
    ## 4 5 months AFTER Mar 2026                   0             2.8                3.4

``` r
acs <- read_csv("data/public/acs_county.csv", show_col_types = FALSE) |>
  filter(year == 2024) |>
  mutate(fips = as.character(fips),
         name = toupper(county)) |>
  select(fips, name, population)

snap_2024 <- snap_county |>
  filter(format(date, "%Y") == "2024", !name %in% c("WPHS", "MNPRAIRIE")) |>
  group_by(name) |>
  summarise(snap_people = mean(people))

fs_2024 <- fs_month |>
  filter(format(date, "%Y") == "2024") |>
  mutate(name = toupper(county)) |>
  group_by(name) |>
  summarise(visits = sum(visits, na.rm = TRUE) / 12)

county_2024 <- acs |>
  inner_join(snap_2024, by = "name") |>
  inner_join(fs_2024, by = "name") |>
  mutate(snap_per_100   = 100 * snap_people / population,
         visits_per_100 = 100 * visits / population)

nrow(county_2024)
```

    ## [1] 81

``` r
cor(county_2024$snap_per_100, county_2024$visits_per_100, method = "spearman")
```

    ## [1] 0.09688347

``` r
county_2024 |>
  mutate(snap_group = ntile(snap_per_100, 3),
         snap_group = factor(snap_group, levels = 1:3,
                             labels = c("Low SNAP use", "Medium SNAP use", "High SNAP use"))) |>
  group_by(snap_group) |>
  summarise(counties       = n(),
            visits_per_100 = mean(visits_per_100)) |>
  ggplot(aes(x = snap_group, y = visits_per_100)) +
  geom_col(fill = "steelblue", width = 0.6) +
  geom_text(aes(label = round(visits_per_100, 1)), vjust = -0.4, size = 5) +
  scale_y_continuous(expand = expansion(mult = c(0, 0.15))) +
  labs(x = NULL,
       y = "Food shelf visits per month per 100 residents",
       title = "Counties with more SNAP use don't have more food shelf use",
       subtitle = "Minnesota counties split into three equal groups by share of residents on SNAP, 2024",
       caption = "Sources: The Food Group; MN DHS SNAP reports; U.S. Census Bureau") +
  theme_minimal()
```

![](Ewura-Work-5_files/figure-gfm/unnamed-chunk-6-1.png)<!-- -->

``` r
ggsave("output/q5_chart2_counties.png", width = 7, height = 5, bg = "white")
```

``` r
steady_sites <- fs_month |>
  filter(date >= as.Date("2022-03-01"), date <= as.Date("2024-02-01"), !is.na(visits)) |>
  count(site) |>
  filter(n == 24) |>
  pull(site)

county_change <- fs_month |>
  filter(site %in% steady_sites, date >= as.Date("2022-03-01"), date <= as.Date("2024-02-01")) |>
  mutate(name   = toupper(county),
         period = ifelse(date < as.Date("2023-03-01"), "before", "after")) |>
  group_by(name, period) |>
  summarise(visits = sum(visits, na.rm = TRUE), .groups = "drop") |>
  pivot_wider(names_from = period, values_from = visits) |>
  mutate(visits_change = 100 * (after / before - 1))

snap_loss <- snap_county |>
  filter(date %in% as.Date(c("2023-02-01", "2023-03-01")),
         !name %in% c("WPHS", "MNPRAIRIE")) |>
  mutate(month = ifelse(date == as.Date("2023-02-01"), "feb", "mar")) |>
  select(name, month, dollars) |>
  pivot_wider(names_from = month, values_from = dollars)

rural <- read_csv("data/public/rural_codes.csv", show_col_types = FALSE) |>
  mutate(fips = as.character(fips))

by_place <- county_change |>
  inner_join(snap_loss, by = "name") |>
  inner_join(acs, by = "name") |>
  left_join(rural, by = "fips") |>
  mutate(snap_lost_per_resident = (feb - mar) / population,
         loss_group = ifelse(snap_lost_per_resident >= median(snap_lost_per_resident),
                             "Lost MORE SNAP per resident", "Lost LESS SNAP per resident"),
         area = ifelse(metro, "Metro", "Rural"))

nrow(by_place)
```

    ## [1] 78

``` r
cor(by_place$snap_lost_per_resident, by_place$visits_change, method = "spearman")
```

    ## [1] 0.1423513

``` r
by_place |>
  group_by(loss_group) |>
  summarise(counties = n(), avg_visits_change = round(mean(visits_change), 1))
```

    ## # A tibble: 2 × 3
    ##   loss_group                  counties avg_visits_change
    ##   <chr>                          <int>             <dbl>
    ## 1 Lost LESS SNAP per resident       39              25.1
    ## 2 Lost MORE SNAP per resident       39              30.6

``` r
by_place |>
  group_by(area) |>
  summarise(counties = n(), avg_visits_change = round(mean(visits_change), 1))
```

    ## # A tibble: 2 × 3
    ##   area  counties avg_visits_change
    ##   <chr>    <int>             <dbl>
    ## 1 Metro       25              29  
    ## 2 Rural       53              27.3

``` r
by_place |>
  group_by(loss_group) |>
  summarise(avg_visits_change = mean(visits_change)) |>
  ggplot(aes(x = loss_group, y = avg_visits_change, fill = loss_group)) +
  geom_col(width = 0.6) +
  geom_text(aes(label = paste0("+", round(avg_visits_change), "%")), vjust = -0.4, size = 5) +
  scale_fill_manual(values = c("steelblue", "grey60")) +
  scale_y_continuous(expand = expansion(mult = c(0, 0.15))) +
  labs(x = NULL, y = "Average change in food shelf visits (%)",
       title = "Did counties that lost more SNAP see bigger food shelf jumps?",
       subtitle = "Change in visits, Mar 2023-Feb 2024 vs. Mar 2022-Feb 2023",
       caption = "Sources: The Food Group; MN DHS SNAP reports; U.S. Census Bureau") +
  theme_minimal() +
  theme(legend.position = "none")
```

![](Ewura-Work-5_files/figure-gfm/unnamed-chunk-7-1.png)<!-- -->

``` r
ggsave("output/q5_chart3_by_place.png", width = 7, height = 5, bg = "white")
```

``` r
library(writexl)
```

    ## Warning: package 'writexl' was built under R version 4.5.3

``` r
write_xlsx(list(statewide_monthly = q5_state,
                before_after      = before_after,
                snap_events       = snap_events,
                counties_2024     = county_2024,
                by_place          = by_place),
           "output/q5_results.xlsx")

list.files("output")
```

    ##  [1] "q1_chart1_need_vs_visits.png"    "q1_chart2_mismatch_counties.png"
    ##  [3] "q1_chart3_distance.png"          "q1_results.xlsx"                
    ##  [5] "q5_chart_before_after.png"       "q5_chart1_before_after.png"     
    ##  [7] "q5_chart1_trends.png"            "q5_chart2_counties.png"         
    ##  [9] "q5_chart3_by_place.png"          "q5_results.xlsx"
