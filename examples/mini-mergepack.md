# Merge packet for diff file examples/sample-pr.diff

- Source: `diff file examples/sample-pr.diff`
- Repo: `examples/mini-repo`
- Files: 3
- Additions/deletions: +23/-1

## Changed Files

| File | Role | Status | Delta |
| --- | --- | --- | ---: |
| `src/checkout.py` | source | modified | +5/-1 |
| `tests/test_checkout.py` | test | added | +16/-0 |
| `.github/workflows/ci.yml` | ci | modified | +2/-0 |

## Verification Commands

- `python -m unittest discover -s tests`
- `python -m compileall src tests`
- `review changed GitHub Actions locally or with a disposable branch run`

## Risk Areas

- CI workflow change: verify permissions, triggers, and artifact behavior.

## Repo Instructions

- `AGENTS.md`: Mini Repo Instructions Keep checkout behavior deterministic. Run unit tests before final review.

## Reviewer Checklist

- [ ] Read the changed files before editing.
- [ ] Confirm the intended behavior from the PR description or issue.
- [ ] Run `python -m unittest discover -s tests`.
- [ ] Run `python -m compileall src tests`.
- [ ] Run `review changed GitHub Actions locally or with a disposable branch run`.
- [ ] Check whether changed tests cover the changed source paths.
- [ ] Review workflow permissions and artifact paths.
- [ ] Summarize residual risk before merge.

## Agent-Ready Prompt

````text
You are reviewing this pull request: Merge packet for diff file examples/sample-pr.diff

Use the repository instructions and changed-file map below. Focus on correctness, tests, regressions, and merge risk. Do not rewrite unrelated code.

Changed files:
- src/checkout.py (source, modified, +5/-1)
- tests/test_checkout.py (test, added, +16/-0)
- .github/workflows/ci.yml (ci, modified, +2/-0)

Repo instructions:
- AGENTS.md: Mini Repo Instructions Keep checkout behavior deterministic. Run unit tests before final review.

Verification commands to consider:
- python -m unittest discover -s tests
- python -m compileall src tests
- review changed GitHub Actions locally or with a disposable branch run

Risk areas:
- CI workflow change: verify permissions, triggers, and artifact behavior.

Diff preview:
```diff
diff --git a/src/checkout.py b/src/checkout.py
index 780bb74..a54a2af 100644
--- a/src/checkout.py
+++ b/src/checkout.py
@@ -1,8 +1,14 @@
 def calculate_total(items, coupon=None):
     total = sum(item["price"] for item in items)
     if coupon == "SAVE10":
-        total = total * 0.9
+        total = total - min(total * 0.1, 50)
+    if coupon == "FREESHIP" and total >= 25:
+        return round(total, 2)
     return round(total, 2)
 
 
 def checkout(items, coupon=None):
+    if not items:
+        raise ValueError("checkout requires at least one item")
     return {"total": calculate_total(items, coupon)}
diff --git a/tests/test_checkout.py b/tests/test_checkout.py
new file mode 100644
index 0000000..5b75197
--- /dev/null
+++ b/tests/test_checkout.py
@@ -0,0 +1,18 @@
+import unittest
+
+from src.checkout import checkout
+
+
+class CheckoutTests(unittest.TestCase):
+    def test_save10_coupon_is_capped(self):
+        self.assertEqual(checkout([{"price": 1000}], "SAVE10")["total"], 950)
+
+    def test_empty_checkout_is_rejected(self):
+        with self.assertRaises(ValueError):
+            checkout([])
+
+
+if __name__ == "__main__":
+    unittest.main()
diff --git a/.github/workflows/ci.yml b/.github/workflows/ci.yml
index 1fd32a1..9a1ef92 100644
--- a/.github/workflows/ci.yml
+++ b/.github/workflows/ci.yml
@@ -7,3 +7,5 @@ jobs:
     steps:
       - uses: actions/checkout@v5
       - run: python -m unittest discover -s tests
+      - name: Compile
+        run: python -m compileall src tests
```

Return findings first, then suggested fixes, then exact commands to run.
````
