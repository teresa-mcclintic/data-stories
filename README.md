# Data Stories — Beta Deployment

Data Stories helps people upload a CSV, find evidence-based discoveries, investigate follow-up questions, and export an interactive story.

## Publish with GitHub + Streamlit Community Cloud

1. Create a **public** GitHub repository named `data-stories` at https://github.com/new .
2. Unzip this package on your computer. In GitHub, choose **Add file → Upload files** and upload the **contents** of this package (not the ZIP file itself). Keep `app.py`, `requirements.txt`, `analysis_engine.py`, `investigate.py`, and the `samples` folder at the top level. GitHub's website may not preserve the hidden `.streamlit` folder when dragging a folder; it is optional and the application still runs without it.
3. Commit the files.
4. Visit https://share.streamlit.io/ and sign in with GitHub. Choose **Create app → Yup, I have an app**.
5. Select your repository, branch `main`, and entrypoint `app.py`. Choose an available URL and deploy.
6. Test the Mt. Bachelor sample, the survey sample, upload a small CSV, investigate a finding, and export My Data Story. Then share the app URL.

If the page fails to load, open Streamlit Community Cloud's app logs. Ensure the `requirements.txt` is in the repository root and all Python modules were uploaded.

## Beta safety note

This is a prototype designed for non-sensitive CSV files. Uploaded data is processed on the hosted application server; the application has no deliberately configured persistent database, but that does not guarantee data is never retained in infrastructure or logs. Do not upload confidential information, personal identifiers, student records, medical data, or other protected information. Do not interpret descriptive patterns as proof of causation. Limit uploads to 8 MB.

## Beta feedback

Use `BETA_FEEDBACK.md` to create a short Google Form or collect written responses. A form is not embedded in the app.
