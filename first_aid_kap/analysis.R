# First-aid knowledge pre/post-test: core analyses in R.
# Usage: load("first_aid.RData") in the same folder, or set data_file below, then source("analysis.R").
# Base R throughout; section 6 also uses lme4 if installed (install.packages("lme4")).

data_file <- "first_aid.RData"
if (!exists("paired")) load(data_file)

a <- subset(paired, analysable)   # matched, both tests complete, no speeders
cat("Analysable participants:", nrow(a), "\n\n")

# 1. Descriptives -----------------------------------------------------------
desc <- function(x) c(n = sum(!is.na(x)), mean = mean(x, na.rm = TRUE), sd = sd(x, na.rm = TRUE),
                      median = median(x, na.rm = TRUE), q1 = unname(quantile(x, .25, na.rm = TRUE)),
                      q3 = unname(quantile(x, .75, na.rm = TRUE)))
print(round(rbind(pre_score = desc(a$pre_score), post_score = desc(a$post_score),
                  change = desc(a$score_change), pre_pct_core = desc(a$pre_pct_core),
                  post_pct_core = desc(a$post_pct_core), change_core = desc(a$pct_change_core)), 2))

# 2. Pre vs post: paired t-test, Wilcoxon signed-rank, effect size (Cohen's dz)
for (v in c("score", "pct_core")) {
  pre <- a[[paste0("pre_", v)]]; post <- a[[paste0("post_", v)]]
  cat("\n==", v, "==\n")
  print(t.test(post, pre, paired = TRUE))
  print(wilcox.test(post, pre, paired = TRUE, exact = FALSE))
  d <- post - pre
  cat("Cohen's dz =", round(mean(d) / sd(d), 2), "\n")
}

# 3. Knowledge level (Bloom) before/after: Bowker test of symmetry -----------
tab <- table(pre = a$pre_know_cat, post = a$post_know_cat)
print(addmargins(tab))
print(mcnemar.test(tab))

# 4. Item-level change: McNemar per item, Holm-adjusted (Q25 versions differ) ----
item_tests <- do.call(rbind, lapply(setdiff(sprintf("Q%02d", 1:36), "Q25"), function(q) {
  x <- a[[paste0("pre_", q, "_c")]]; y <- a[[paste0("post_", q, "_c")]]
  ok <- !is.na(x) & !is.na(y)
  t2 <- table(factor(x[ok], 0:1), factor(y[ok], 0:1))
  data.frame(item = q, n = sum(ok), pre_pct = round(100 * mean(x[ok]), 1),
             post_pct = round(100 * mean(y[ok]), 1),
             p = if (t2[1, 2] + t2[2, 1] > 0) mcnemar.test(t2)$p.value else NA)
}))
item_tests$p_holm <- p.adjust(item_tests$p, "holm")
item_tests$doubtful <- item_tests$item %in% items$item[items$doubtful]
print(item_tests, digits = 3)

# 5. Change by district and adjusted post-test (ANCOVA) ----------------------
print(kruskal.test(score_change ~ region, data = a))
fit <- lm(post_score ~ pre_score + region, data = a)
print(anova(fit))
print(summary(fit)$coefficients[1:2, ])

# 6. Item-level mixed logistic model (accounts for random item allocation) ---
# P(correct) ~ phase, random intercepts for person and item.
if (requireNamespace("lme4", quietly = TRUE)) {
  il <- subset(item_responses, selected & analysable & !doubtful_item)
  m <- lme4::glmer(correct ~ phase + (1 | pid) + (1 | item), data = il, family = binomial,
                   control = lme4::glmerControl(optimizer = "bobyqa"))
  print(summary(m)$coefficients)
  b <- lme4::fixef(m)["phasepost"]; se <- sqrt(vcov(m)["phasepost", "phasepost"])
  cat("OR post vs pre =", round(exp(b), 2), " 95% CI", round(exp(b + c(-1.96, 1.96) * se), 2), "\n")
} else {
  message("Install lme4 to run the item-level mixed model.")
}
