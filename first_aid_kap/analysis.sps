* Encoding: UTF-8.
* First-aid knowledge pre/post-test: core analyses on the paired file.
* Open first_aid_paired.sav first (File > Open), or edit the path below.
* GET FILE='first_aid_paired.sav'.

SET UNICODE=ON.
FILTER OFF.
USE ALL.
SELECT IF (analysable = 1).

* 1. Descriptives and normality of the change score.
DESCRIPTIVES VARIABLES=pre_score post_score score_change pre_pct_core post_pct_core pct_change_core
  /STATISTICS=MEAN STDDEV MIN MAX.
EXAMINE VARIABLES=score_change pct_change_core
  /PLOT HISTOGRAM NPPLOT /STATISTICS DESCRIPTIVES.

* 2. Pre vs post: paired t-test (primary) and Wilcoxon signed-rank (robustness).
T-TEST PAIRS=pre_score pre_pct_core WITH post_score post_pct_core (PAIRED).
NPAR TESTS /WILCOXON=pre_score pre_pct_core WITH post_score post_pct_core (PAIRED).

* 3. Knowledge level (Bloom) before/after: marginal homogeneity.
CROSSTABS /TABLES=pre_know_cat BY post_know_cat /CELLS=COUNT TOTAL.
NPAR TESTS /MH=pre_know_cat WITH post_know_cat (PAIRED).

* 4. Item-level change: McNemar per item (Q25 differs between versions - do not interpret).
NPAR TESTS /MCNEMAR=
  pre_Q01_c pre_Q02_c pre_Q03_c pre_Q04_c pre_Q05_c pre_Q06_c pre_Q07_c
  pre_Q08_c pre_Q09_c pre_Q10_c pre_Q11_c pre_Q12_c pre_Q13_c pre_Q14_c
  pre_Q15_c pre_Q16_c pre_Q17_c pre_Q18_c pre_Q19_c pre_Q20_c pre_Q21_c
  pre_Q22_c pre_Q23_c pre_Q24_c pre_Q26_c pre_Q27_c pre_Q28_c pre_Q29_c
  pre_Q30_c pre_Q31_c pre_Q32_c pre_Q33_c pre_Q34_c pre_Q35_c pre_Q36_c
  WITH
  post_Q01_c post_Q02_c post_Q03_c post_Q04_c post_Q05_c post_Q06_c post_Q07_c
  post_Q08_c post_Q09_c post_Q10_c post_Q11_c post_Q12_c post_Q13_c post_Q14_c
  post_Q15_c post_Q16_c post_Q17_c post_Q18_c post_Q19_c post_Q20_c post_Q21_c
  post_Q22_c post_Q23_c post_Q24_c post_Q26_c post_Q27_c post_Q28_c post_Q29_c
  post_Q30_c post_Q31_c post_Q32_c post_Q33_c post_Q34_c post_Q35_c post_Q36_c (PAIRED).

* 5. Change by district (region): one-way ANOVA / Kruskal-Wallis.
ONEWAY score_change BY region /STATISTICS DESCRIPTIVES.
NPAR TESTS /K-W=score_change BY region(1 22).

* 6. Adjusted change (ANCOVA form): post score adjusted for pre score and district.
UNIANOVA post_score BY region WITH pre_score
  /PRINT=PARAMETER ETASQ /DESIGN=pre_score region.
