"""Data Stories: approachable, evidence-first CSV discovery (Streamlit)."""
from __future__ import annotations

import html
from pathlib import Path

import pandas as pd
import plotly.express as px
import streamlit as st

from analysis_engine import discover, fmt, load_csv, plot_finding, profile
from investigate import suggest_followups, render_investigation
from data_context import infer_label, infer_grain, replace_fields, style_figure, column_role
from ai_assistant import plan_question, calculate, UnsupportedQuestion

ROOT = Path(__file__).resolve().parent
st.set_page_config(page_title='Data Stories', page_icon='📈', layout='wide', initial_sidebar_state='expanded')
st.markdown('''<style>
html, body, [class*="css"] {font-family: Arial, Helvetica, sans-serif;}
.block-container {padding-top: 2rem;max-width: 1160px;}
h1,h2,h3 {letter-spacing: -.025em;}
[data-testid="stMetric"] {background:#f3f6fa;padding:14px;border-radius:12px;}
</style>''', unsafe_allow_html=True)


def choose_data() -> tuple[bytes | None, str]:
    st.sidebar.title('Data Stories')
    st.sidebar.caption('You bring the data. Discover its story.')
    choice = st.sidebar.radio('Start with', ['Upload my CSV', 'Explore a sample'], label_visibility='collapsed')
    if choice == 'Upload my CSV':
        up = st.sidebar.file_uploader('Choose a CSV file', type=['csv'], help='CSV files up to 8 MB')
        return (up.getvalue(), up.name) if up is not None else (None, '')
    demos = {'Mt. Bachelor monthly snowfall': 'mt_bachelor_monthly.csv', 'Fictional community survey': 'sample_survey.csv'}
    demos = {k: v for k, v in demos.items() if (ROOT / 'samples' / v).exists()}
    if not demos:
        st.sidebar.info('Sample datasets are being added. Please upload a CSV.')
        return None, ''
    selected = st.sidebar.selectbox('Sample dataset', list(demos))
    target = ROOT / 'samples' / demos[selected]
    return target.read_bytes(), selected


def story_download(story: list[dict], source: str) -> str:
    cards=[]
    for entry in story:
        caption=html.escape(entry['title'])
        desc=html.escape(entry['summary'])
        evidence=html.escape(entry['evidence'])
        origin=html.escape(entry.get('origin', 'Discovery'))
        cards.append(f'<section><p><small>{origin}</small></p><h2>{caption}</h2><p>{desc}</p><p><small>{evidence}</small></p>{entry["chart"]}</section>')
    return ('<!doctype html><html><head><meta charset="utf-8"><title>My Data Story</title>'
            '<style>body{font-family:Arial,Helvetica,sans-serif;max-width:900px;margin:36px auto;padding:0 20px;color:#243247}'
            'section{padding:24px 0;border-top:1px solid #ddd}h1{color:#193457}small{color:#536278}</style></head><body>'
            f'<h1>My Data Story</h1><p>Source: {html.escape(source)}</p>'
            '<p>Findings are descriptive and based on the data supplied, not explanations of causation.</p>'
            + ''.join(cards) + '</body></html>')

raw, source_name = choose_data()
st.title('Discover the story in your data')
st.write('Upload a CSV to see patterns worth exploring, then investigate them with interactive charts. No spreadsheet skills needed.')

if raw is None:
    st.info('Choose **Upload my CSV** in the sidebar, or switch to **Explore a sample** to try it now.')
    st.stop()

try:
    df = load_csv(raw)
except (ValueError, pd.errors.EmptyDataError, UnicodeError) as exc:
    st.error(f'We could not open that file: {exc}')
    st.stop()

# Prevent findings from an earlier uploaded dataset appearing in a new story.
identity = (source_name, len(raw), __import__('hashlib').sha256(raw).hexdigest())
if st.session_state.get('data_identity') != identity:
    st.session_state.data_identity = identity
    st.session_state.story = []
    st.session_state.investigation_notes = {}
    st.session_state.selected_finding = None
    st.session_state.investigate_choice = None
    st.session_state.followup_question_picker = None
    st.session_state.discovery_question_picker = None
    st.session_state.column_labels = {col: infer_label(col) for col in df.columns}
    st.session_state.dataset_title = source_name.replace('.csv', '').replace('_',' ').strip()
    st.session_state.row_grain = infer_grain(df.columns)
    st.session_state.ai_answer = None
    st.session_state.ai_count = 0

p = profile(df)
st.caption(f'Dataset: **{st.session_state.dataset_title}** · CSV is processed in the running app. No account or database is used.')

# Optional confirmation: descriptions change presentation, not the source data or maths.
with st.expander('✏️ Understand your data — review names and meanings', expanded=False):
    st.write('We suggested readable labels for your columns. Correct anything that does not match your data.')
    st.text_input('Dataset title', key='dataset_title')
    grains = ['observation', 'day', 'month', 'year', 'person', 'transaction']
    st.selectbox(
        'What does each row represent?', grains,
        format_func=lambda g: {'observation':'One observation / record', 'day':'One day',
            'month':'One month', 'year':'One year', 'person':'One person',
            'transaction':'One transaction'}[g],
        key='row_grain',
        help='This helps us phrase questions correctly. It does not silently change how values are calculated.',
    )
    st.caption('Original column names remain intact. Labels affect questions, charts, and menus, not calculations.')
    st.dataframe(pd.DataFrame([
        {'CSV field': col, 'Suggested label': st.session_state.column_labels.get(col, infer_label(col)),
         'Detected type': column_role(df,col)}
        for col in df.columns
    ]), hide_index=True, use_container_width=True)
    chosen_col = st.selectbox('Choose a column to rename', df.columns.tolist(), key='label_editor_column',
                              format_func=lambda col: st.session_state.column_labels.get(col, col))
    new_label = st.text_input('Show this column as', value=st.session_state.column_labels.get(chosen_col, infer_label(chosen_col)), key='label_editor_' + str(df.columns.get_loc(chosen_col)))
    if st.button('Apply label', key='apply_label'):
        if not new_label.strip():
            st.warning('Please provide a nonempty label.')
        else:
            st.session_state.column_labels[chosen_col] = new_label.strip()
            st.rerun()

def pretty(field: str) -> str:
    return st.session_state.column_labels.get(field, infer_label(field))

def phrase(text: str) -> str:
    return replace_fields(text, st.session_state.column_labels)

def pretty_chart(fig):
    return style_figure(fig, st.session_state.column_labels)


with st.expander('About this dataset and its limitations', expanded=False):
    st.write('This tool describes patterns and associations; it cannot establish causes, verify the accuracy of source measurements, or guarantee statistical significance.')
    st.write('Each row is treated as one observation. Repeated measurements or category totals may need additional context. Numeric group comparisons use means.')
    if 'snowfall' in source_name.lower() or 'bachelor' in source_name.lower():
        st.write('The sample Mt. Bachelor records are modeled Open-Meteo snowfall estimates, not official resort measurements. The final month may be incomplete.')
    st.warning('Do not upload confidential, personal, medical, student, or other protected data to a publicly hosted version without an appropriate privacy review.')


# Keep the discovery experience simple: advanced filtering belongs in Explore.
# Partial periods are excluded so they do not distort comparisons.
filtered = df.copy()
if 'coverage' in filtered.columns:
    filtered = filtered[filtered['coverage'].astype(str).str.lower() != 'partial'].copy()
if filtered.empty:
    st.warning('No complete observations are available. Check the Data & quality section.')
    st.stop()

def friendly(name: str) -> str:
    return pretty(name)

def question_for(f, frame):
    r = f['recipe']
    kind = r['type']
    if kind == 'time':
        v = friendly(r['value']).lower()
        d = r['date']
        vals = frame[d].dropna()
        grain = st.session_state.row_grain
        if grain == 'month':
            return f'How has monthly {v} changed over time?'
        if grain == 'day':
            return f'How has daily {v} changed over time?'
        if grain == 'year':
            return f'How has annual {v} changed over time?'
        if len(vals) and vals.dt.year.nunique() > 10:
            return f'How has {v} varied over the years?'
        return f'How has {v} changed over time?'
    if kind == 'groups':
        return f'How does {friendly(r["value"]).lower()} differ across {friendly(r["category"]).lower()}?'
    if kind == 'distribution':
        return f'What is typical for {friendly(r["value"]).lower()}?'
    if kind == 'relationship':
        return f'Are {friendly(r["x"]).lower()} and {friendly(r["y"]).lower()} connected?'
    return 'Are there gaps in the dataset?'

def guidance_for(f):
    kind = f['recipe']['type']
    if kind == 'time':
        return ('Explore the long-term pattern and compare meaningful time periods. '
                'A comparison of the first and last *months* is not evidence of a yearly trend.')
    if kind == 'groups':
        return 'Compare categories and examine how typical values differ.'
    if kind == 'distribution':
        return 'Look at common values, the spread, and unusual observations.'
    if kind == 'relationship':
        return 'Examine how two measurements vary together, without assuming cause and effect.'
    return 'Understand missing records before drawing conclusions.'

nfiltered = profile(filtered)

# Prominent navigation: explain what each section does before asking users to choose.
# Buttons are keyboard accessible, and the active page stays highlighted.
if 'active_page' not in st.session_state:
    st.session_state.active_page = 'Discover'

st.markdown('### What would you like to do?')
nav_items = [
    ('Discover', '🔎 Discover', 'Find questions worth exploring'),
    ('Explore', '📊 Explore', 'Make your own comparisons'),
    ('My Data Stories', '📖 My Data Stories', 'Save and share your findings'),
    ('Data & Quality', '🗂️ Data & Quality', 'Inspect and check your data'),
]
def change_page(page: str) -> None:
    # Streamlit runs callbacks before rendering widgets on the next rerun,
    # keeping the selected section and its visual highlighting in sync.
    st.session_state.active_page = page

nav_cols = st.columns(4, gap='small')
for col, (page, label, explanation) in zip(nav_cols, nav_items):
    with col:
        st.button(
            label,
            key='nav_' + page.replace(' ', '_').replace('&', 'and'),
            type='primary' if st.session_state.active_page == page else 'secondary',
            use_container_width=True,
            on_click=change_page,
            args=(page,),
        )
        st.caption(explanation)
st.divider()

def render_ai_panel() -> None:
    st.markdown('### ✨ Ask Data Stories AI')
    with st.expander('Ask your own question about this dataset', expanded=False):
        st.caption('Try a question in your own words. AI chooses a supported analysis; Python calculates the numbers and draws the chart.')
        try:
            ai_key = st.secrets.get('OPENAI_API_KEY', '')
            ai_model = st.secrets.get('OPENAI_MODEL', 'gpt-4.1-mini')
        except (FileNotFoundError, KeyError):
            ai_key = ''
            ai_model = 'gpt-4.1-mini'
        if not ai_key:
            st.info('AI is not configured yet. The discovery and follow-up tools above still work. An app administrator can add OPENAI_API_KEY in Streamlit app settings → Secrets.')
        else:
            st.caption('Privacy: your question and column names/types are sent to OpenAI. Dataset rows are not sent. Do not ask questions containing private information.')
            ai_consent = st.checkbox('I understand what is sent to the AI service', key='ai_consent')
            if st.session_state.get('ai_count',0) >= 5:
                st.warning('You have reached the five-question limit for this session.')
            else:
                with st.form('ai_question_form', clear_on_submit=False):
                    ai_question = st.text_input('Your question about the data', max_chars=400,
                        placeholder='Example: How did snowfall differ by decade?')
                    ai_submit = st.form_submit_button('Ask Data Stories AI', disabled=not ai_consent)
                if ai_submit:
                    if not ai_question.strip():
                        st.warning('Please type a question.')
                    else:
                        st.session_state.ai_count += 1
                        st.session_state.ai_answer = None
                        try:
                            with st.spinner('Planning an analysis and calculating the answer…'):
                                ai_plan = plan_question(ai_question,filtered,
                                    st.session_state.column_labels,ai_key,ai_model)
                                ai_summary,ai_fig = calculate(filtered,ai_plan,
                                    st.session_state.column_labels)
                                st.session_state.ai_answer = (ai_question,ai_summary,ai_fig)
                        except UnsupportedQuestion as exc:
                            st.info(str(exc))
                        except Exception as exc:
                            # Provide a safe, actionable error rather than hiding every failure.
                            # Do not display request headers, API keys or raw exceptions.
                            import logging
                            logging.getLogger(__name__).exception('Data Stories AI request failed')
                            try:
                                from openai import AuthenticationError, PermissionDeniedError, RateLimitError, APIConnectionError, APITimeoutError, BadRequestError, NotFoundError
                            except ImportError:
                                AuthenticationError = PermissionDeniedError = RateLimitError = APIConnectionError = APITimeoutError = BadRequestError = NotFoundError = ()
                            if isinstance(exc, AuthenticationError):
                                st.error('OpenAI rejected the API key. Check the OPENAI_API_KEY value in this app’s Streamlit Secrets.')
                            elif isinstance(exc, PermissionDeniedError):
                                st.error('This OpenAI API project does not have permission to use the selected model. Check its project access and model setting.')
                            elif isinstance(exc, RateLimitError):
                                st.error('OpenAI returned a usage or quota limit. Check your API project’s billing, available credits, and rate limits.')
                            elif isinstance(exc, (APIConnectionError, APITimeoutError)):
                                st.error('The app could not connect to OpenAI. Please try again or check the Streamlit logs.')
                            elif isinstance(exc, (BadRequestError, NotFoundError)):
                                st.error('The OpenAI request was rejected. Confirm OPENAI_MODEL is supported by your API project (try gpt-4.1-mini) and consult the Streamlit app logs.')
                            else:
                                st.error(f'The analysis encountered an unexpected error ({type(exc).__name__}). Open the Streamlit app logs for details. No API key is shown here.')
            if st.session_state.get('ai_answer'):
                asked, answer, figure = st.session_state.ai_answer
                st.markdown('**Your question:** ' + asked)
                st.plotly_chart(figure,use_container_width=True,key='ai_result_chart')
                st.write(answer)
                st.caption('Numbers and visualization are computed by Python from the supplied CSV. Not every question is supported yet.')
                st.markdown('#### Add this investigation to your story')
                ai_note = st.text_area(
                    'Your interpretation (optional)',
                    key='ai_story_note',
                    height=85,
                    placeholder='What do you find interesting about this result?',
                )
                if st.button('📖 Save to My Data Story', key='save_ai_investigation', type='primary'):
                    # Reuse the existing story format and preserve the interactive chart.
                    import hashlib
                    fingerprint = hashlib.sha256(
                        (asked + '\\n' + answer).encode('utf-8')
                    ).hexdigest()
                    ident = ('ai_investigation', fingerprint)
                    if any(entry.get('ident') == ident for entry in st.session_state.story):
                        st.info('This AI investigation is already saved to My Data Story.')
                    else:
                        st.session_state.story.append({
                            'ident': ident,
                            'origin': 'AI-Assisted Investigation',
                            'title': asked,
                            'summary': answer + ('\\n\\nYour interpretation: ' + ai_note.strip() if ai_note.strip() else ''),
                            'evidence': 'Descriptive results calculated from the uploaded dataset using Python; AI assisted with selecting an analysis. Interpretations do not establish causation.',
                            'chart': figure.to_html(full_html=False, include_plotlyjs=False),
                        })
                        st.success('Saved to My Data Story. Open My Data Stories to review or download it.')


if st.session_state.active_page == 'Discover':
    findings = discover(filtered, limit=5)
    chosen = st.session_state.get('selected_finding')
    if chosen is not None and not (0 <= chosen < len(findings)):
        st.session_state.selected_finding = None
        st.session_state.investigate_choice = None
        st.session_state.discovery_question_picker = None
        st.session_state.followup_question_picker = None
        chosen = None

    st.subheader('What would you like to discover?')
    st.caption(f'{st.session_state.dataset_title} · {len(filtered):,} records · {len(df.columns)} columns')

    def choose_discovery_question() -> None:
        new_choice = st.session_state.discovery_question_picker
        if new_choice != st.session_state.get('selected_finding'):
            st.session_state.selected_finding = new_choice
            st.session_state.investigate_choice = None
            st.session_state.followup_question_picker = None

    if not findings:
        st.info('Not enough usable numeric data for automatic discoveries. Try Explore or Ask Data Stories AI below.')
    else:
        st.selectbox(
            'Choose a question to investigate',
            options=list(range(len(findings))),
            index=None,
            placeholder='Select a discovery question…',
            format_func=lambda idx: question_for(findings[idx], filtered),
            key='discovery_question_picker',
            on_change=choose_discovery_question,
            label_visibility='collapsed',
            help='Select a question to see its chart and relevant follow-up investigations.',
        )

    # Keep both menus together, even before a discovery is selected.
    st.markdown('### Where would you like to go next?')
    options = suggest_followups(filtered, findings[chosen]) if findings and chosen is not None else []
    if chosen is None:
        st.caption('Choose a discovery question above to unlock relevant follow-up questions.')
    elif not options:
        st.caption('No follow-up questions are available for this discovery. You can still use AI below.')
    else:
        st.caption('Choose a related question to investigate a different perspective.')

    def choose_followup_question() -> None:
        st.session_state.investigate_choice = st.session_state.followup_question_picker

    st.selectbox(
        'Choose a follow-up question',
        options=list(range(len(options))),
        index=None,
        placeholder='Select a discovery above first…' if chosen is None
                    else ('No follow-up questions available' if not options
                          else 'Select a follow-up question…'),
        format_func=lambda idx: f"{options[idx]['lane']} — {phrase(options[idx]['question'])}",
        key='followup_question_picker',
        on_change=choose_followup_question,
        label_visibility='collapsed',
        disabled=chosen is None or not options,
        help='Follow-ups depend on the discovery selected above.',
    )

    if findings and chosen is not None:
        st.divider()
        st.markdown('### Your selected investigation')

        finding = findings[chosen]
        st.subheader(question_for(finding, filtered))
        st.write(guidance_for(finding))
        if finding['recipe']['type'] == 'time':
            st.info('Monthly data often have seasonal patterns. Use **Change perspective** below for yearly or decade comparisons; compare only complete periods.')
        else:
            st.write(phrase(finding['summary']))
        st.plotly_chart(pretty_chart(plot_finding(filtered, finding)), use_container_width=True, key='selected_chart')
        with st.expander('How was this finding calculated?'):
            st.write(phrase(finding['evidence']))
            st.write(phrase(finding['question']))
        if st.button('Save this discovery to My Data Story', key='save_discovery'):
            ident = ('discovery', finding['title'])
            if any(item.get('ident') == ident for item in st.session_state.story):
                st.info('This discovery is already saved.')
            else:
                fig = pretty_chart(plot_finding(filtered, finding))
                st.session_state.story.append({
                    'ident': ident, 'title': question_for(finding, filtered),
                    'summary': guidance_for(finding), 'evidence': phrase(finding['evidence']),
                    'chart': fig.to_html(full_html=False, include_plotlyjs=False)
                })
                st.success('Saved to My Data Story.')
        i = st.session_state.get('investigate_choice')
        if i is not None and 0 <= i < len(options):
            option = options[i]
            with st.container(border=True):
                st.markdown('#### ' + phrase(option['question']))
                outcome = render_investigation(filtered, finding, option, key=f'investigation_{chosen}_{i}')
                if outcome is not None:
                    explanation, fig = outcome
                    fig = pretty_chart(fig)
                    st.plotly_chart(fig, use_container_width=True, key=f'investigation_chart_{chosen}_{i}')
                    st.write(phrase(explanation))
                    note = st.text_area('Your interpretation (optional)', key=f'note_{chosen}_{i}', height=75)
                    if st.button('Save this investigation to My Data Story', key=f'save_followup_{chosen}_{i}'):
                        ident = ('investigation', finding['title'], option['id'])
                        if any(item.get('ident') == ident for item in st.session_state.story):
                            st.info('This investigation is already saved.')
                        else:
                            st.session_state.story.append({
                                'ident': ident, 'title': phrase(option['question']),
                                'summary': 'Follow-up to: ' + question_for(finding, filtered) + (' — ' + note if note.strip() else ''),
                                'evidence': phrase(explanation), 'chart': fig.to_html(full_html=False, include_plotlyjs=False)
                            })
                            st.success('Saved to My Data Story.')



    st.divider()
    render_ai_panel()

if st.session_state.active_page == 'Explore':
    st.subheader('Explore your own question')
    st.write('Choose what you want to investigate. The app will make a suitable interactive chart.')
    chart_type=st.selectbox('I want to…',['See how something changes over time','Compare groups','Understand a distribution','See whether two measures are related'])
    nums=nfiltered['numeric']
    if chart_type.startswith('See how'):
        if nfiltered['dates'] and nums:
            date=st.selectbox('Date column',nfiltered['dates'],key='explore_date',format_func=pretty)
            value=st.selectbox('Value to follow',nums,key='explore_time_value',format_func=pretty)
            aggregation=st.selectbox('When dates repeat, calculate', ['Average','Total','Median'], help='Choose Total only for additive quantities such as sales or snowfall, not temperatures or percentages.')
            grouped=filtered[[date,value]].dropna().groupby(date,as_index=False)[value].agg({'Average':'mean','Total':'sum','Median':'median'}[aggregation]).sort_values(date)
            fig=px.line(grouped,x=date,y=value,markers=True,title=f'{aggregation} {value} over time')
        else:
            st.info('This view needs a recognizable date column and a numeric column. Dates like 2024-01-01 are supported.')
            fig=None
    elif chart_type=='Compare groups':
        if nfiltered['categories'] and nums:
            cat=st.selectbox('Group by',nfiltered['categories'],format_func=pretty)
            val=st.selectbox('Compare which number?',nums,format_func=pretty)
            measure=st.radio('Calculate', ['Average','Total','Count'],horizontal=True)
            grouped=filtered.groupby(cat,as_index=False,observed=True)[val].agg({'Average':'mean','Total':'sum','Count':'count'}[measure]).sort_values(val,ascending=False)
            fig=px.bar(grouped,x=cat,y=val,title=f'{measure} of {val} by {cat}')
        else:
            st.info('This view needs a category column and a numeric column.')
            fig=None
    elif chart_type=='Understand a distribution':
        if nums:
            val=st.selectbox('Which numeric field?',nums,key='hist_val',format_func=pretty)
            bins=st.slider('Number of histogram bins',5,60,25)
            fig=px.histogram(filtered,x=val,nbins=bins,title=f'How is {val} distributed?')
        else:
            st.info('This view needs a numeric column.')
            fig=None
    else:
        if len(nums)>=2:
            x=st.selectbox('First measure',nums,format_func=pretty)
            y=st.selectbox('Second measure',[n for n in nums if n!=x],format_func=pretty)
            fig=px.scatter(filtered.head(10000),x=x,y=y,title=f'{x} compared with {y}')
            st.caption('A relationship on a chart does not establish cause and effect. Scatterplots show at most 10,000 records.')
        else:
            st.info('This view needs at least two numeric columns.')
            fig=None
    if fig is not None:
        fig.update_layout(template='plotly_white',font_family='Arial')
        fig = pretty_chart(fig)
        st.plotly_chart(fig,use_container_width=True,key='explore_chart')
        st.download_button('Download interactive chart (HTML)',fig.to_html(full_html=True,include_plotlyjs=True).encode('utf-8'), 'data-stories-chart.html','text/html')

    st.divider()
    render_ai_panel()

if st.session_state.active_page == 'My Data Stories':
    st.subheader('My Data Story')
    st.write('Collect discoveries and follow-up investigations here, then download a self-contained HTML report with interactive charts. The story is held in this browser session only.')
    story=st.session_state.story
    if not story:
        st.info('Nothing saved yet. Open Discover and save a finding or a follow-up investigation.')
    else:
        for i, item in enumerate(story):
            a,b=st.columns([5,1])
            a.markdown(f'**{i+1}. {item["title"]}**')
            if item.get('origin'):
                a.caption(item['origin'])
            a.write(item['summary'])
            if b.button('Remove',key=f'remove_{i}'):
                st.session_state.story.pop(i)
                st.rerun()
        report=story_download(story,source_name)
        # Include Plotly JS exactly once so report works offline.
        from plotly.offline import get_plotlyjs
        report=report.replace('</head>',f'<script>{get_plotlyjs()}</script></head>')
        st.download_button('Download my interactive Data Story (HTML)',report.encode('utf-8'),file_name='my_data_story.html',mime='text/html')
        if st.button('Clear my story'):
            st.session_state.story=[]
            st.rerun()

if st.session_state.active_page == 'Data & Quality':
    st.subheader('Understand your dataset')
    st.write('Inspect numerical summaries and check for data quality issues before drawing conclusions.')
    if nfiltered['numeric']:
        st.markdown('#### Numeric summary')
        summary = filtered[nfiltered['numeric']].describe().T.round(2)
        summary = summary.rename(index=st.session_state.column_labels)
        st.dataframe(summary, use_container_width=True)
    else:
        st.info('No numeric columns were detected in this dataset.')

    col1,col2,col3=st.columns(3)
    col1.metric('Rows',f'{len(filtered):,}')
    col2.metric('Columns',filtered.shape[1])
    col3.metric('Duplicate rows',f'{nfiltered["duplicate_rows"]:,}')

    st.markdown('#### Data preview')
    st.dataframe(filtered.head(100).rename(columns=st.session_state.column_labels),
                 use_container_width=True,hide_index=True)
    st.caption('Preview shows up to 100 rows after filtering.')

    st.markdown('#### Missing values by column')
    missing=filtered.isna().sum().sort_values(ascending=False).rename('Missing values')
    missing.index=[pretty(col) for col in missing.index]
    st.dataframe(missing.to_frame(),use_container_width=True)
    st.download_button('Download filtered data (CSV)',filtered.to_csv(index=False).encode('utf-8'),file_name='filtered_data.csv',mime='text/csv')

st.divider()
st.caption('Data Stories v5 preview · Rule-based discovery and follow-up investigations · No AI API · Associations do not establish causation.')
