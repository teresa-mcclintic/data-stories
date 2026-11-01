"""Data Stories: approachable, evidence-first CSV discovery (Streamlit)."""
from __future__ import annotations

import html
from pathlib import Path

import pandas as pd
import plotly.express as px
import streamlit as st

from analysis_engine import discover, fmt, load_csv, plot_finding, profile
from investigate import suggest_followups, render_investigation

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
        cards.append(f'<section><h2>{caption}</h2><p>{desc}</p><p><small>{evidence}</small></p>{entry["chart"]}</section>')
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

p = profile(df)
st.caption(f'Dataset: **{source_name}** · CSV is processed in the running app. No account or database is used.')

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
    return str(name).replace('_', ' ').replace('-', ' ').strip().capitalize()

def question_for(f, frame):
    r = f['recipe']
    kind = r['type']
    if kind == 'time':
        v = friendly(r['value']).lower()
        d = r['date']
        vals = frame[d].dropna()
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

if st.session_state.active_page == 'Discover':
    findings = discover(filtered, limit=5)
    chosen = st.session_state.get('selected_finding')
    if chosen is None or chosen >= len(findings):
        st.subheader('What would you like to discover?')
        st.write('Choose one interesting question. We will show you a visualization, explain what it means, and offer new directions to explore.')
        st.caption(f'{len(filtered):,} records · {len(df.columns)} columns · {source_name}')
        if not findings:
            st.info('Not enough usable numeric data for automatic discoveries. Try the Explore tab.')
        for idx, finding in enumerate(findings):
            with st.container(border=True):
                st.markdown(f'#### {idx+1}. {question_for(finding, filtered)}')
                st.write(guidance_for(finding))
                if st.button('Explore this question →', key=f'open_{idx}', type='primary' if idx == 0 else 'secondary'):
                    st.session_state.selected_finding = idx
                    st.session_state.investigate_choice = None
                    st.rerun()
        st.caption('Already have a question? Use the Explore tab to choose your own variables.')
    else:
        finding = findings[chosen]
        if st.button('← All discovery questions', key='return_to_gallery'):
            st.session_state.selected_finding = None
            st.session_state.investigate_choice = None
            st.rerun()
        st.subheader(question_for(finding, filtered))
        st.write(guidance_for(finding))
        if finding['recipe']['type'] == 'time':
            st.info('Monthly data often have seasonal patterns. Use **Change perspective** below for yearly or decade comparisons; compare only complete periods.')
        else:
            st.write(finding['summary'])
        st.plotly_chart(plot_finding(filtered, finding), use_container_width=True, key='selected_chart')
        with st.expander('How was this finding calculated?'):
            st.write(finding['evidence'])
            st.write(finding['question'])
        if st.button('Save this discovery to My Data Story', key='save_discovery'):
            ident = ('discovery', finding['title'])
            if any(item.get('ident') == ident for item in st.session_state.story):
                st.info('This discovery is already saved.')
            else:
                fig = plot_finding(filtered, finding)
                st.session_state.story.append({
                    'ident': ident, 'title': question_for(finding, filtered),
                    'summary': guidance_for(finding), 'evidence': finding['evidence'],
                    'chart': fig.to_html(full_html=False, include_plotlyjs=False)
                })
                st.success('Saved to My Data Story.')
        st.divider()
        st.markdown('### Where would you like to go next?')
        st.caption('Choose a new perspective. Questions are offered only when supported by the available data.')
        options = suggest_followups(filtered, finding)
        if not options:
            st.info('No other follow-up questions are available. Try Explore for a custom chart.')
        else:
            for lane, icon in [('Dig deeper','🔎'), ('Change perspective','📅'), ('Make connections','🔗')]:
                lane_items = [(i,o) for i,o in enumerate(options) if o['lane'] == lane]
                if lane_items:
                    st.markdown(f'**{icon} {lane}**')
                    for i, option in lane_items:
                        if st.button(option['question'], key=f'follow_{chosen}_{i}', use_container_width=True):
                            st.session_state.investigate_choice = i
                            st.rerun()
            i = st.session_state.get('investigate_choice')
            if i is not None and 0 <= i < len(options):
                option = options[i]
                with st.container(border=True):
                    st.markdown('#### ' + option['question'])
                    outcome = render_investigation(filtered, finding, option, key=f'investigation_{chosen}_{i}')
                    if outcome is not None:
                        explanation, fig = outcome
                        st.plotly_chart(fig, use_container_width=True, key=f'investigation_chart_{chosen}_{i}')
                        st.write(explanation)
                        note = st.text_area('Your interpretation (optional)', key=f'note_{chosen}_{i}', height=75)
                        if st.button('Save this investigation to My Data Story', key=f'save_followup_{chosen}_{i}'):
                            ident = ('investigation', finding['title'], option['id'])
                            if any(item.get('ident') == ident for item in st.session_state.story):
                                st.info('This investigation is already saved.')
                            else:
                                st.session_state.story.append({
                                    'ident': ident, 'title': option['question'],
                                    'summary': 'Follow-up to: ' + question_for(finding, filtered) + (' — ' + note if note.strip() else ''),
                                    'evidence': explanation, 'chart': fig.to_html(full_html=False, include_plotlyjs=False)
                                })
                                st.success('Saved to My Data Story.')

if st.session_state.active_page == 'Explore':
    st.subheader('Explore your own question')
    st.write('Choose what you want to investigate. The app will make a suitable interactive chart.')
    chart_type=st.selectbox('I want to…',['See how something changes over time','Compare groups','Understand a distribution','See whether two measures are related'])
    nums=nfiltered['numeric']
    if chart_type.startswith('See how'):
        if nfiltered['dates'] and nums:
            date=st.selectbox('Date column',nfiltered['dates'],key='explore_date')
            value=st.selectbox('Value to follow',nums,key='explore_time_value')
            aggregation=st.selectbox('When dates repeat, calculate', ['Average','Total','Median'], help='Choose Total only for additive quantities such as sales or snowfall, not temperatures or percentages.')
            grouped=filtered[[date,value]].dropna().groupby(date,as_index=False)[value].agg({'Average':'mean','Total':'sum','Median':'median'}[aggregation]).sort_values(date)
            fig=px.line(grouped,x=date,y=value,markers=True,title=f'{aggregation} {value} over time')
        else:
            st.info('This view needs a recognizable date column and a numeric column. Dates like 2024-01-01 are supported.')
            fig=None
    elif chart_type=='Compare groups':
        if nfiltered['categories'] and nums:
            cat=st.selectbox('Group by',nfiltered['categories'])
            val=st.selectbox('Compare which number?',nums)
            measure=st.radio('Calculate', ['Average','Total','Count'],horizontal=True)
            grouped=filtered.groupby(cat,as_index=False,observed=True)[val].agg({'Average':'mean','Total':'sum','Count':'count'}[measure]).sort_values(val,ascending=False)
            fig=px.bar(grouped,x=cat,y=val,title=f'{measure} of {val} by {cat}')
        else:
            st.info('This view needs a category column and a numeric column.')
            fig=None
    elif chart_type=='Understand a distribution':
        if nums:
            val=st.selectbox('Which numeric field?',nums,key='hist_val')
            bins=st.slider('Number of histogram bins',5,60,25)
            fig=px.histogram(filtered,x=val,nbins=bins,title=f'How is {val} distributed?')
        else:
            st.info('This view needs a numeric column.')
            fig=None
    else:
        if len(nums)>=2:
            x=st.selectbox('First measure',nums)
            y=st.selectbox('Second measure',[n for n in nums if n!=x])
            fig=px.scatter(filtered.head(10000),x=x,y=y,title=f'{x} compared with {y}')
            st.caption('A relationship on a chart does not establish cause and effect. Scatterplots show at most 10,000 records.')
        else:
            st.info('This view needs at least two numeric columns.')
            fig=None
    if fig is not None:
        fig.update_layout(template='plotly_white',font_family='Arial')
        st.plotly_chart(fig,use_container_width=True,key='explore_chart')
        st.download_button('Download interactive chart (HTML)',fig.to_html(full_html=True,include_plotlyjs=True).encode('utf-8'), 'data-stories-chart.html','text/html')

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
    st.write('Inspect the original columns and look for issues before drawing conclusions.')
    st.dataframe(filtered.head(100),use_container_width=True,hide_index=True)
    st.caption('Preview shows up to 100 rows after filtering.')
    col1,col2,col3=st.columns(3)
    col1.metric('Rows',f'{len(filtered):,}')
    col2.metric('Columns',filtered.shape[1])
    col3.metric('Duplicate rows',f'{nfiltered["duplicate_rows"]:,}')
    st.markdown('#### Missing values by column')
    missing=filtered.isna().sum().sort_values(ascending=False).rename('Missing values')
    st.dataframe(missing.to_frame(),use_container_width=True)
    if nfiltered['numeric']:
        st.markdown('#### Numeric summary')
        st.dataframe(filtered[nfiltered['numeric']].describe().T.round(2),use_container_width=True)
    st.download_button('Download filtered data (CSV)',filtered.to_csv(index=False).encode('utf-8'),file_name='filtered_data.csv',mime='text/csv')

st.divider()
st.caption('Data Stories v5 preview · Rule-based discovery and follow-up investigations · No AI API · Associations do not establish causation.')
