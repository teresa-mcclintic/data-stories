# Data Stories — Version 5 preview

A question-first CSV explorer built with Streamlit. Upload a public, non-sensitive CSV, select a suggested question, see a chart, and follow **Dig deeper**, **Change perspective**, or **Make connections**. Explore custom charts and collect findings into an interactive HTML report.

## Preview in Streamlit Community Cloud

This branch is **version-5**, not the public beta's **main** branch. To create a separate preview:

1. Visit https://share.streamlit.io/ and choose **Create app**.
2. Choose **Yup, I have an app** and select repository `teresa-mcclintic/data-stories`.
3. Set branch to `version-5` (not `main`) and main file to `app.py`.
4. Choose a different app URL, e.g. `data-stories-preview.streamlit.app` if available, and deploy.
5. Use **Try a sample** to test the snowfall and fictional survey data. Try uploading your own non-sensitive CSV.
6. Return to the GitHub draft pull request to review the changes. **Do not merge** until you are satisfied.

Your existing Streamlit app based on `main` stays on Version 4 unless the pull request is merged.

## Run locally

```powershell
python -m pip install -r requirements.txt
python -m streamlit run app.py
```

## What's new

- A gallery of up to five discoverable questions instead of a wall of charts.
- A single investigation view with a clear way back to all questions.
- Prominent follow-up questions organized by three lenses.
- Simpler sidebar and approachable titles.
- Exclusion of incomplete months from the provided snowfall example.
- Retained Explore, My Data Story, and Data & quality sections.

## Testing and limitations

The interface still needs a full end-to-end browser test in Streamlit. The original numerical engine and follow-up logic are kept; automatic year/month inference and user-chosen aggregations should be checked against realistic datasets before wider rollout. This is a **descriptive data exploration** tool, not a statistically validated or causal inference system.

Do not upload confidential, identifiable student, medical, financial, or other protected information to the public app without a privacy and security review. The CSV is processed on Streamlit's hosting server. The Mt. Bachelor example is modeled ERA5 snowfall, not official resort observations.
