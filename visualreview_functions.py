import pandas as pd
import matplotlib.pyplot as plt
import ipywidgets as widgets

def show_event(idx, runs_list, df, station_id, current_out, btn_back, btn_true, btn_false):
    current_out.clear_output()
    start, end = runs_list[idx]
    window = df.loc[start - pd.Timedelta(days=1): end + pd.Timedelta(days=1), "value"]
    with current_out:
        fig, ax = plt.subplots(figsize=(10, 4))
        ax.plot(window.index, window.values, lw=1)
        ax.axvspan(start, end, color="red", alpha=0.3)
        ax.set_title(
            f"{station_id} ({idx+1}/{len(runs_list)}) — "
            f"{start:%Y-%m-%d %H:%M} to {end:%Y-%m-%d %H:%M}")
        plt.tight_layout()
        plt.show()
    btn_back.disabled = (idx == 0)
    # Buttons always visible while reviewing
    btn_true.layout.visibility  = "visible"
    btn_false.layout.visibility = "visible"

def update_progress(progress, all_results):
    progress.value = len(all_results)

def log_result(history_out, text):
    with history_out:
        print(text)

def next_event(state, runs_list, df, station_id, current_out, history_out,
               progress, all_results, btn_back, btn_true, btn_false):
    state['i'] += 1
    if state['i'] < len(runs_list):
        btn_back.disabled = False  # always re-enable once we're past event 0
        show_event(state['i'], runs_list, df, station_id,
                   current_out, btn_back, btn_true, btn_false)
    else:
        # All events classified — hide buttons
        current_out.clear_output()
        btn_true.layout.visibility  = "hidden"
        btn_false.layout.visibility = "hidden"
        with history_out:
            print("🎉 Done!")

def prev_event(state, runs_list, df, station_id, current_out, history_out,
               progress, all_results, btn_back, btn_true, btn_false):
    if state['i'] > 0:
        state['i'] -= 1
        if len(all_results) > state['i']:
            all_results.pop()
        update_progress(progress, all_results)
        show_event(state['i'], runs_list, df, station_id,
                   current_out, btn_back, btn_true, btn_false)
        btn_true.layout.visibility  = "visible"
        btn_false.layout.visibility = "visible"
        with history_out:
            print(f"↩️ Went back to event {state['i']+1}")

def on_true(b, state, runs_list, station_id, all_results, history_out,
            progress, df, current_out, btn_back, btn_true, btn_false):
    start, end = runs_list[state['i']]
    record = {"station": station_id, "start": start, "end": end, "real": True}
    if len(all_results) > state['i']:
        all_results[state['i']] = record
    else:
        all_results.append(record)
    log_result(history_out, f"✅ {state['i']+1}: {start} – {end} → True")
    update_progress(progress, all_results)
    next_event(state, runs_list, df, station_id, current_out, history_out,
               progress, all_results, btn_back, btn_true, btn_false)

def on_false(b, state, runs_list, station_id, all_results, history_out,
             progress, df, current_out, btn_back, btn_true, btn_false):
    start, end = runs_list[state['i']]
    record = {"station": station_id, "start": start, "end": end, "real": False}
    if len(all_results) > state['i']:
        all_results[state['i']] = record
    else:
        all_results.append(record)
    log_result(history_out, f"❌ {state['i']+1}: {start} – {end} → False")
    update_progress(progress, all_results)
    next_event(state, runs_list, df, station_id, current_out, history_out,
               progress, all_results, btn_back, btn_true, btn_false)

def build_ui(runs_list, df, station_id, all_results):
    state = {'i': 0}
    history_out = widgets.Output()
    current_out = widgets.Output()
    progress = widgets.IntProgress(
        value=0, min=0, max=len(runs_list),
        description="Progress:", bar_style="")
    btn_true  = widgets.Button(description="True",  button_style="success")
    btn_false = widgets.Button(description="False", button_style="danger")
    btn_back  = widgets.Button(description="⬅ Back", button_style="warning")
    buttons   = widgets.HBox([btn_back, btn_true, btn_false])
    container = widgets.VBox([progress, history_out, current_out, buttons])

    kw = dict(state=state, runs_list=runs_list, station_id=station_id,
              all_results=all_results, history_out=history_out, progress=progress,
              df=df, current_out=current_out, btn_back=btn_back,
              btn_true=btn_true, btn_false=btn_false)

    btn_true.on_click(lambda b: on_true(b, **kw))
    btn_false.on_click(lambda b: on_false(b, **kw))
    btn_back.on_click(lambda b: prev_event(
        state=state, runs_list=runs_list, df=df, station_id=station_id,
        current_out=current_out, history_out=history_out, progress=progress,
        all_results=all_results, btn_back=btn_back, btn_true=btn_true, btn_false=btn_false))

    return container, lambda: show_event(0, runs_list, df, station_id,
                                          current_out, btn_back, btn_true, btn_false)