# Held-out report: frozen vs learned vs baselines

Train window 2018-03-31 to 2022-12-31, held-out window 2023-03-31 to 2024-12-31. 40 train companies, 10 held out for good.
Accuracy is higher-is-better. Brier is lower-is-better. Only cells where both the frozen and the learned agent produced a resolved grade are counted.

## fundamentals

Corrections applied in training: 160. Model version mubit:claude-haiku-5-5+fundamentals-lessons-v0 to mubit:claude-haiku-5-5+fundamentals-lessons-v160. Dropped calls (held-out, frozen/learned): 105/105.

### All companies (n = 295)

| | accuracy | Brier |
|---|---|---|
| frozen | 60.0% | 0.243 |
| learned | 58.0% | 0.241 |
| always_yes | 40.0% | 0.600 |
| base_rate | 60.0% | 0.250 |

Learned minus frozen: accuracy -2.0 pts, Brier -0.002.

### Companies seen in training (n = 234)

| | accuracy | Brier |
|---|---|---|
| frozen | 59.8% | 0.244 |
| learned | 57.3% | 0.242 |
| always_yes | 40.2% | 0.598 |
| base_rate | 59.8% | 0.250 |

Learned minus frozen: accuracy -2.6 pts, Brier -0.002.

### Held-out companies (never seen) (n = 61)

| | accuracy | Brier |
|---|---|---|
| frozen | 60.7% | 0.242 |
| learned | 60.7% | 0.240 |
| always_yes | 39.3% | 0.607 |
| base_rate | 60.7% | 0.247 |

Learned minus frozen: accuracy +0.0 pts, Brier -0.002.

## scenarios

Corrections applied in training: 162. Model version mubit:claude-haiku-5-5+scenarios-lessons-v0 to mubit:claude-haiku-5-5+scenarios-lessons-v162. Dropped calls (held-out, frozen/learned): 8/8.

### All companies (n = 392)

| | accuracy | Brier |
|---|---|---|
| frozen | 63.8% | 0.552 |
| learned | 57.9% | 0.606 |
| always_base | 51.5% | 0.969 |
| base_rate | 25.0% | 0.680 |

Learned minus frozen: accuracy -5.9 pts, Brier +0.053.

### Companies seen in training (n = 312)

| | accuracy | Brier |
|---|---|---|
| frozen | 64.1% | 0.547 |
| learned | 57.7% | 0.603 |
| always_base | 50.0% | 1.000 |
| base_rate | 26.0% | 0.679 |

Learned minus frozen: accuracy -6.4 pts, Brier +0.056.

### Held-out companies (never seen) (n = 80)

| | accuracy | Brier |
|---|---|---|
| frozen | 62.5% | 0.573 |
| learned | 58.8% | 0.616 |
| always_base | 57.5% | 0.850 |
| base_rate | 21.2% | 0.685 |

Learned minus frozen: accuracy -3.7 pts, Brier +0.043.

---

*Research tool, not financial advice.*
