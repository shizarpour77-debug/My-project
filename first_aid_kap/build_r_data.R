# Build typed R datasets from the CSVs written by clean_first_aid.py.
# Usage: Rscript build_r_data.R output
# Writes output/R/: first_aid.RData (all objects), one .rds per object, data_dictionary.csv.
# Base R only; no packages needed.

args <- commandArgs(trailingOnly = TRUE)
out_dir <- if (length(args)) args[1] else "output"
in_dir <- file.path(out_dir, "r_input")
r_dir <- file.path(out_dir, "R")
dir.create(r_dir, showWarnings = FALSE)

# encoding= marks text as UTF-8 without re-encoding, so Persian text survives any locale.
rd <- function(f) read.csv(file.path(in_dir, f), encoding = "UTF-8", stringsAsFactors = FALSE,
                           check.names = FALSE)
attempts <- rd("attempts.csv")
paired <- rd("paired.csv")
item_responses <- rd("item_responses.csv")
items <- rd("items.csv")
var_labels <- rd("var_labels.csv")
value_labels <- rd("value_labels.csv")
cleaning_log <- rd("cleaning_log.csv")

# ---- helpers ---------------------------------------------------------------
yes_no_vars <- c("nid_valid", "flag_region_conflict", "selected", "has_pre", "has_post", "matched",
                 "analysable", "flag_empty", "flag_incomplete", "flag_speeder", "flag_long",
                 "flag_outside_period")
strip_prefix <- function(v) sub("^(pre|post)_", "", v)

type_vars <- function(d) {
  for (v in names(d)) {
    base <- strip_prefix(v)
    x <- d[[v]]
    if (base %in% yes_no_vars) {
      d[[v]] <- as.logical(x)
    } else if (base == "region") {
      d[[v]] <- factor(x, levels = 1:22, labels = sprintf("D%02d", 1:22))
    } else if (base == "phase") {
      d[[v]] <- factor(x, levels = 1:2, labels = c("pre", "post"))
    } else if (base == "know_cat") {
      d[[v]] <- factor(x, levels = 1:3, labels = c("poor", "moderate", "good"), ordered = TRUE)
    } else if (base %in% c("start_dt", "end_dt")) {
      d[[v]] <- as.POSIXct(ifelse(x == "", NA, x), tz = "Asia/Tehran", format = "%Y-%m-%d %H:%M:%S")
    } else if (grepl("^Q[0-9]{2}_r$", base)) {
      lab <- value_labels[value_labels$dataset == "attempts" & value_labels$variable == base &
                            value_labels$code != 9, ]
      x[x == 9] <- NA
      d[[v]] <- factor(x, levels = lab$code, labels = lab$label)
    } else if (grepl("^Q[0-9]{2}_c$", base) || base %in% c("pid", "attempt_id", "attempt_no",
                                                           "n_attempts", "n_answered", "score",
                                                           "score_platform", "score_change")) {
      d[[v]] <- as.integer(x)
    }
  }
  d
}

add_labels <- function(d, dataset) {
  lab <- var_labels[var_labels$dataset == dataset, ]
  for (v in intersect(names(d), lab$variable)) attr(d[[v]], "label") <- lab$label[lab$variable == v]
  d
}

# ---- typed datasets --------------------------------------------------------
attempts <- add_labels(type_vars(attempts), "attempts")
paired <- add_labels(type_vars(paired), "paired")

# Tidy item-level data: one row per presented item per attempt.
resp_lab <- value_labels[value_labels$dataset == "attempts" & grepl("^Q[0-9]{2}_r$", value_labels$variable), ]
resp_lab$item <- substr(resp_lab$variable, 1, 3)
key <- paste(item_responses$item, item_responses$response)
item_responses$response_text <- resp_lab$label[match(key, paste(resp_lab$item, resp_lab$code))]
item_responses$response_text[item_responses$response == 9] <- NA
item_responses$response <- as.integer(ifelse(item_responses$response == 9, NA, item_responses$response))
item_responses$correct <- as.integer(item_responses$correct)
item_responses$phase <- factor(item_responses$phase, levels = 1:2, labels = c("pre", "post"))
item_responses$item <- factor(item_responses$item, levels = sprintf("Q%02d", 1:36))
item_responses$selected <- as.logical(item_responses$selected)
item_responses$doubtful_item <- as.logical(item_responses$doubtful_item)
item_responses <- merge(item_responses, paired[, c("pid", "region", "analysable")], by = "pid", all.x = TRUE)
item_responses <- item_responses[order(item_responses$pid, item_responses$attempt_id, item_responses$item), ]
rownames(item_responses) <- NULL
attr(item_responses$correct, "label") <- "1 = correct, 0 = wrong (only presented items)"
attr(item_responses$response, "label") <- "Option code: 1 = keyed answer, 2-4 = distractors"

items$doubtful <- as.logical(items$doubtful)
names(items) <- c("item", "question_post", "key", "pre_n", "pre_pct_correct", "pre_item_rest_r",
                  "post_n", "post_pct_correct", "post_item_rest_r", "paired_n", "note", "doubtful",
                  "question_pre")

# ---- data dictionary ---------------------------------------------------------
dict <- do.call(rbind, lapply(c("attempts", "paired", "item_responses"), function(nm) {
  d <- get(nm)
  data.frame(dataset = nm, variable = names(d),
             class = vapply(d, function(x) class(x)[1], ""),
             label = vapply(d, function(x) if (is.null(attr(x, "label"))) "" else attr(x, "label"), ""),
             levels = vapply(d, function(x) if (is.factor(x)) paste(levels(x), collapse = " | ") else "", ""),
             n_missing = vapply(d, function(x) sum(is.na(x)), 0L))
}))

# ---- save ----------------------------------------------------------------
objs <- c("attempts", "paired", "item_responses", "items", "dict", "cleaning_log")
for (o in objs) saveRDS(get(o), file.path(r_dir, paste0(o, ".rds")))
save(list = objs, file = file.path(r_dir, "first_aid.RData"))
write.csv(dict, file.path(r_dir, "data_dictionary.csv"), row.names = FALSE, fileEncoding = "UTF-8")
cat(sprintf("%-15s %6d rows x %3d cols\n", objs, sapply(objs, function(o) nrow(get(o))),
            sapply(objs, function(o) ncol(get(o)))), sep = "")
