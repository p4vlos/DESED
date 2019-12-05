# -*- coding: utf-8 -*-
#########################################################################
# Initial software
# Copyright Nicolas Turpault, Romain Serizel, Justin Salamon, Ankit Parag Shah, 2019, v1.0
# This software is distributed under the terms of the License MIT
#########################################################################

import jams
import numpy as np
import os
import os.path as osp
import shutil
import glob
import soundfile as sf
import pprint
import pandas as pd

from Logger import LOG


def create_folder(folder, delete_if_exists=False):
    if delete_if_exists:
        if os.path.exists(folder):
            shutil.rmtree(folder)
            os.mkdir(folder)

    if not os.path.exists(folder):
        os.makedirs(folder)


pp = pprint.PrettyPrinter()
def pprint(x):
    pp.pprint(x)


def choose_class(class_params):
    tmp = 0
    inter = []
    for i in range(len(class_params['event_prob'])):
        tmp += class_params['event_prob'][i]
        inter.append(tmp)
    ind = np.random.uniform()*100
    return class_params['event_class'][np.argmax(np.asarray(inter)>ind)]


def choose_file(class_path):
    source_files = sorted(glob.glob(os.path.join(class_path, "*")))
    source_files = [f for f in source_files if os.path.isfile(f)]
    ind = np.random.randint(0, len(source_files))
    return source_files[ind]


def add_event(sc, class_lbl, duration, fg_folder):
    source_time_dist = 'const'
    source_time = 0.0
    event_duration_min = 0.25

    snr_dist = 'uniform'
    snr_min = 6
    snr_max = 30

    pitch_dist = 'uniform'
    pitch_min = -3.0
    pitch_max = 3.0

    time_stretch_dist = 'uniform'
    time_stretch_min = 1
    time_stretch_max = 1

    chosen_file = choose_file(os.path.join(fg_folder, class_lbl))
    file_duration = round(sf.info(chosen_file).duration, 6)  # round because Scaper uses sox with round 6 digits
    if "_nOn_nOff" in class_lbl:
        LOG.debug('no onset/offset')
        sc.add_event(label=('const', class_lbl),
                     source_file=('const', chosen_file),
                     source_time=('uniform', 0, np.maximum(file_duration - duration, 0)),
                     event_time=('const', 0),
                     event_duration=('const', duration),
                     snr=(snr_dist, snr_min, snr_max),
                     pitch_shift=(pitch_dist, pitch_min, pitch_max),
                     time_stretch=(time_stretch_dist, time_stretch_min, time_stretch_max))
    elif "_nOn" in class_lbl:
        LOG.debug('no onset')
        source_start = np.random.uniform(0, file_duration - event_duration_min)
        sc.add_event(label=('const', class_lbl),
                     source_file=('const', chosen_file),
                     source_time=('const', source_start),
                     event_time=('const', 0),
                     event_duration=('const', np.minimum(duration, file_duration - source_start)),
                     snr=(snr_dist, snr_min, snr_max),
                     pitch_shift=(pitch_dist, pitch_min, pitch_max),
                     time_stretch=(time_stretch_dist, time_stretch_min, time_stretch_max))
    elif "_nOf" in class_lbl:
        LOG.debug('no offset')
        event_start = np.random.uniform(max(0, duration - file_duration), duration - event_duration_min)
        event_length = duration - event_start
        sc.add_event(label=('const', class_lbl),
                     source_file=('const', chosen_file),
                     source_time=(source_time_dist, source_time),
                     event_time=('const', event_start),
                     event_duration=('const', event_length),
                     snr=(snr_dist, snr_min, snr_max),
                     pitch_shift=(pitch_dist, pitch_min, pitch_max),
                     time_stretch=(time_stretch_dist, time_stretch_min, time_stretch_max))
    else:
        event_start = np.random.uniform(0, duration - event_duration_min)
        event_length = min(file_duration, duration - event_start)
        sc.add_event(label=('const', class_lbl),
                     source_file=('const', chosen_file),
                     source_time=(source_time_dist, source_time),
                     event_time=('const', event_start),
                     event_duration=('const', event_length),
                     snr=(snr_dist, snr_min, snr_max),
                     pitch_shift=(pitch_dist, pitch_min, pitch_max),
                     time_stretch=(time_stretch_dist, time_stretch_min, time_stretch_max))
    return sc


def rm_high_polyphony(folder, max_polyphony=3, save_csv_associated=None):
    """ Remove the files having a too high polyphony in the deignated folder

    Args:
        folder: str, path to the folder containing scaper generated sounds (JAMS files) in which to remove the files.
        max_polyphony: int, the maximum number of sounds that can be hear at the same time (polyphony).
        save_csv_associated: str, optional, the path to generate the csv files of associated sounds.

    Returns:
        None

    """
    # Select training
    i = 0
    df = pd.DataFrame(columns=['scaper', 'bg', 'fg'])
    fnames_to_rmv = []
    for jam_file in sorted(glob.glob(osp.join(folder, "*.jams"))):
        param = jams.load(jam_file)
        ann = param.annotations.search(namespace='scaper')[0]
        if ann['sandbox']['scaper']['polyphony_max'] < max_polyphony:
            fg = [osp.basename(line.value['source_file']) for line in ann.data]
            bg = osp.basename(ann.data[0].value['source_file'])
            fname = osp.basename(jam_file)
            df_tmp = pd.DataFrame(np.array([[fname, bg, ",".join(fg)]]), columns=['scaper', 'bg', 'fg'])
            df = df.append(df_tmp, ignore_index=True)
            i += 1
        else:
            fnames_to_rmv.append(jam_file)
    if save_csv_associated is not None:
        df.to_csv(save_csv_associated, sep="\t", index=False)

    LOG.info(f"{i} files with less than {max_polyphony} overlapping events. Deleting others...")
    for fname in fnames_to_rmv:
        names = glob.glob(osp.splitext(fname)[0] + ".*")
        for file in names:
            os.remove(file)


def sanity_check(df, length_sec=None):
    if length_sec is not None:
        df['offset'].clip(upper=length_sec, inplace=True)
    df['onset'].clip(lower=0, inplace=True)
    df = df.round(3)
    return df


def get_data(file, wav_file=None, background_label=False):
    if wav_file is not None:
        data, sr = sf.read(wav_file)
        length_sec = data.shape[0] / sr
    else:
        length_sec = None

    fn, ext = osp.splitext(file)
    if ext == ".txt":
        if background_label:
            raise NotImplementedError("Impossible to add the background event from the txt file. "
                                      "Information not in the txt file")
        df = pd.read_csv(file, sep='\t', names=["onset", "offset", "event_label"])
    elif ext == ".jams":
        df = get_df_from_jams(file, background_label)
    else:
        raise NotImplementedError("Only txt and jams generated by Scaper can be loaded with get_data")

    return df, length_sec


def post_process_df(df, length_sec, min_dur_event=0.250, min_dur_inter=0.150):
    fix_count = 0
    df = sanity_check(df, length_sec)
    df = df.sort_values('onset')
    for class_name in df['event_label'].unique():
        LOG.debug(class_name)
        i = 0
        while i is not None:
            indexes = df[df['event_label'] == class_name].index
            ref_onset = df.loc[indexes[i], 'onset']
            ref_offset = df.loc[indexes[i], 'offset']
            if ref_offset - ref_onset < min_dur_event:
                ref_offset = ref_onset + min_dur_event
                # Too short event, and at the offset (onset sorted),
                # so if it overlaps with others, they are also too short.
                if ref_offset > length_sec:
                    df = df.drop(indexes[i:])
                    fix_count += len(indexes[i:])
                    break
                else:
                    df.loc[indexes[i], 'offset'] = ref_onset + min_dur_event
            j = i + 1
            while j < len(indexes):
                if df.loc[indexes[j], 'offset'] < ref_offset:
                    df = df.drop(indexes[j])
                    LOG.debug("Merging overlapping annotations")
                    fix_count += 1
                elif df.loc[indexes[j], 'onset'] - ref_offset < min_dur_inter:
                    df.loc[indexes[i], 'offset'] = df.loc[indexes[j], 'offset']
                    ref_offset = df.loc[indexes[j], 'offset']
                    df = df.drop(indexes[j])
                    LOG.debug("Merging consecutive annotation with pause" +
                          "<150ms")
                    fix_count += 1
                elif df.loc[indexes[j], 'onset'] - ref_onset < min_dur_event + min_dur_inter:
                    df.loc[indexes[i], 'offset'] = df.loc[indexes[j], 'offset']
                    ref_offset = df.loc[indexes[j], 'offset']
                    df = df.drop(indexes[j])
                    LOG.debug("Merging consecutive annotations" +
                          " with onset diff<400ms")
                    fix_count += 1
                else:
                    # Quitting the loop
                    break
                j += 1
            i += 1
            if i >= len(df[df['event_label'] == class_name].index):
                i = None
    df = df.sort_values('onset')
    return df, fix_count


def post_processing_annotations(dir, wavdir=None, output_folder=None, output_csv=None, min_dur_event=0.250,
                                min_dur_inter=0.150, background_label=False):
    """ clean the .txt files of each file. It is the same processing as the real data
    - overlapping events of the same class are mixed
    - if silence < 150ms between two conscutive events of the same class, they are mixed
    - if event < 250ms, the event lasts 250ms

    Args:
        dir: str, directory path where the XXX.txt files are.
        wavdir: str, directory path where the associated XXX.wav audio files are (associated with .txt files)
        output_folder: str, optional, folder in which to put the checked files
        output_csv: str, optional, csv with all the annotations concatenated
        min_dur_event: float, optional in sec, minimum duration of an event
        min_dur_inter: float, optional in sec, minimum duration between 2 events

    Returns:
        None
    """
    if wavdir is None:
        wavdir = dir
    fix_count = 0
    LOG.info("Correcting annotations ... \n"
          "* annotations with negative duration will be removed\n" +
          "* annotations with duration <250ms will be extended on the offset side)")

    if output_folder is not None:
        create_folder(output_folder)

    if output_csv is not None:
        df_single = pd.DataFrame()

    if background_label:
        pattern = '*.jams'
    else:
        pattern = '*.txt'

    for fn in glob.glob(osp.join(dir, pattern)):
        LOG.debug(fn)
        df, length_sec = get_data(fn, osp.join(wavdir, osp.splitext(osp.basename(fn))[0] + '.wav'),
                                  background_label=background_label)

        df, fc = post_process_df(df, length_sec, min_dur_event, min_dur_inter)
        fix_count += fc

        if output_folder is not None:
            df[['onset', 'offset', 'event_label']].to_csv(osp.join(output_folder, os.path.basename(fn)),
                header=False, index=False, sep="\t")
        if output_csv is not None:
            df['filename'] = osp.join(osp.splitext(fn)[0] + '.wav')
            df_single = df_single.append(df[['filename', 'onset', 'offset', 'event_label']], ignore_index=True)

    if output_csv:
        df_single.to_csv(output_csv, index=False, sep="\t", float_format="%.3f")

    LOG.info(f"================\nFixed {fix_count} problems\n================")


def get_df_from_jams(jam_file, background_label=False, return_length=False):
    csv_data = []
    param = jams.load(jam_file)
    ann = param['annotations'][0]
    for obs in ann.data:
        if obs.value['role'] == 'foreground' or (background_label and obs.value['role'] == 'background'):
            csv_data.append(
                [obs.time, obs.time + obs.duration, obs.value['label']])
    df = pd.DataFrame(csv_data, columns=["onset", "offset", "event_label"])

    if return_length:
        return df, ann.duration
    else:
        return df


def generate_csv_from_jams(list_jams, csv_out, post_process=True, background_label=False):
    """ In scaper generate, they create txt files, using the same idea, we create a single csv file.

    Returns:

    """
    final_df = pd.DataFrame()
    for jam_file in list_jams:
        fbase = osp.basename(jam_file)
        df, length = get_df_from_jams(jam_file, background_label=background_label, return_length=True)

        if post_process:
            df, _ = post_process_df(df, length)

        df["filename"] = fbase
        final_df = final_df.append(df[['filename', 'onset', 'offset', 'event_label']], ignore_index=True)

    final_df = final_df.sort_values(by=["filename", "onset"])
    final_df.to_csv(csv_out, sep="\t", index=False, float_format="%.3f")


if __name__ == '__main__':
    rm_high_polyphony("/Users/nturpaul/Documents/Seafile/DCASE/Desed_synthetic/eval/soundscapes_generated_ls/ls_30dB")
    post_processing_annotations("/Users/nturpaul/Documents/Seafile/DCASE/Desed_synthetic/training/soundscapes_generated",
                                "/Users/nturpaul/Documents/Seafile/DCASE/Desed_synthetic/training/soundscapes_generated",
                                output_folder="/Users/nturpaul/Documents/Seafile/DCASE/Desed_synthetic/training/soundscapes_generated_fixed2")
