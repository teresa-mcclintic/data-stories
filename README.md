# Data Stories — Version 6 AI preview

Version 6 builds on Version 5 and adds an **optional** AI question box available at the top of every section, even before choosing a discovery.

## What it does

- Users ask a question about an uploaded CSV in ordinary language.
- An OpenAI model looks only at **column names, inferred types, readable labels, and the user's question** and proposes one supported analysis plan. It does not receive CSV rows.
- Python validates that plan against the real columns, computes descriptive statistics locally, and draws an interactive Plotly chart.
- Supported analyses: time trends (original dates, calendar years, decades, months); category comparisons; numeric distributions; and scatterplot/correlation comparisons.
- Unsupported questions—prediction, causal inference, specific filtering, many seasonal comparisons, statistical tests—are declined rather than answered with invented numbers.
- No code supplied by AI is executed. AI produces an analysis plan, not the answer.

The descriptive answer is produced by Python, not a free-form AI interpretation. Future versions may expand supported question types and verified explanations.

## Deploy as a separate preview

1. In Streamlit Community Cloud, create a **new** app based on `teresa-mcclintic/data-stories`, selecting branch **`version-6`** and main file **`app.py`**.
2. Give it a distinct subdomain. **Do not repoint the existing Version 5 or public Version 4 apps**.
3. Visit https://platform.openai.com/api-keys to create an API key. OpenAI API usage is billed separately from ChatGPT subscriptions.
4. In the **Version 6 app's** Streamlit **App settings → Secrets**, add:

```toml
OPENAI_API_KEY = "your-key-here"
OPENAI_MODEL = "gpt-4.1-mini"
```

**Never save the real key to GitHub, README, screenshots, or in chat.** The key is read server-side from Streamlit secrets.

5. Reload the preview. Choose the Mt. Bachelor or fictional survey sample, open **Ask Data Stories AI** near the top of the page, acknowledge the privacy notice, and ask a question such as **How has snowfall changed from decade to decade?**
6. Confirm the generated chart and numerical summary; test with a question requiring unsupported operations to see the safe refusal.

Without the API key, the regular Version 5 functionality remains available and the AI box explains that setup is needed.

## Privacy and cost limits

- **Not sent to OpenAI:** uploaded CSV rows, charts, calculated values, saved stories.
- **Sent to OpenAI:** question text, column names, data types, and display labels. Column names and questions can themselves be sensitive; use only non-sensitive datasets in this beta.
- API responses request `store=False`.
- Up to **five AI submissions per Streamlit browser session** in this prototype. This is **not** strong abuse prevention; public rollout requires authentication, durable per-user quotas, billing alerts, and ideally a server-side rate limiter.
- Set a tight API budget before exposing the service to anyone else.

## Current limitations

Data Stories remains a descriptive exploratory tool. Even a validated chart might not fully answer a nuanced natural-language question. In particular, annual/decade charts derived from monthly data require complete calendar years; season-year analyses aren't yet offered. For unexpected behavior, verify against the underlying CSV. Correlations do not establish causation.

## Local development

```powershell
python -m pip install -r requirements.txt
python -m streamlit run app.py
```

Local secrets should be stored outside the repository in `.streamlit/secrets.toml`. Do not commit that file.

The public site stays on `main` (Version 4) and the earlier preview remains on `version-5`.
