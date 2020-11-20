import numpy as np
import torch
from soundnet import SoundNet
from util import preprocess, load_audio
import os
from dcase_util.datasets import TUTAcousticScenes_2017_DevelopmentSet, TUTAcousticScenes_2017_EvaluationSet
from joblib import Parallel, delayed


def load_DCASE_development():
    if not os.path.exists("DCASE"):
        os.mkdir("DCASE")
    db = TUTAcousticScenes_2017_DevelopmentSet(data_path="DCASE", filelisthash_exclude_dirs="features")
    db.initialize()
    return db

def load_DCASE_evaluation():
    if not os.path.exists("DCASE"):
        os.mkdir("DCASE")
    db = TUTAcousticScenes_2017_EvaluationSet(data_path="DCASE", filelisthash_exclude_dirs="features")
    db.initialize()
    return db

def features_extraction_DCASE(db):
    features_dir = os.path.join(db.local_path, "features")
    if not os.path.exists(features_dir):
        os.mkdir(features_dir)
    model = SoundNet()
    model.load_state_dict(torch.load("sound8.pth"))
    model.eval()
    for audio_filename in db.audio_files:
        features_filename = get_features_filename(features_dir, audio_filename)
        if not os.path.exists(features_filename):
            x = extract_features(audio_filename, model)
            save_features(x, features_filename)

def get_features_filename(features_dir, audio_filename):
    parent, last = os.path.split(audio_filename)
    features_filename_last = last.replace(".wav", ".npz")
    features_filename = os.path.join(features_dir, features_filename_last)
    return features_filename

def save_features(x, feature_filename):
    features_name = {"layer"+str(i) : x[i] for i in range(len(x))}
    np.savez(feature_filename, **features_name)

def extract_features(audio_filename, model):
    sound, sr = load_audio(audio_filename, sr=44100)
    sound = preprocess(sound, config={"load_size": 44100*10, "phase": "extract"})
    sound = torch.as_tensor(sound)
    with torch.no_grad():
        features = model.forward(sound)
    features = features[:7] + [features[7][0], features[7][1]]
    features = [f.numpy().reshape(-1) for f in features]
    return features


def get_k_fold(db, n_jobs=1):
    for fold in db.folds():
        i = 0
        train, evaluation = [], []
        for label in db.scene_labels():
            for item in db.train(fold=fold).filter(scene_label=label):
                train.append(i)
                i += 1
        for label in db.scene_labels():
            for item in db.eval(fold=fold).filter(scene_label=label):
                evaluation.append(i)
                i += 1
        yield np.array(train), np.array(evaluation)

def get_training_data(db, layer, n_jobs=1):
    features_dir = os.path.join(db.local_path, "features")
    def get_fold(k):
        X, y = [], []
        for label in db.scene_labels():
            for item in db.train(fold=k).filter(scene_label=label):
                features_filename = get_features_filename(features_dir, item.filename)
                x = np.load(features_filename)["layer"+str(layer)]
                X.append(x)
                y.append(label)
        for label in db.scene_labels():
            for item in db.eval(fold=k).filter(scene_label=label):
                features_filename = get_features_filename(features_dir, item.filename)
                x = np.load(features_filename)["layer"+str(layer)]
                X.append(x)
                y.append(label)
        return X, y
    res = Parallel(n_jobs=n_jobs)(delayed(get_fold)(k) for k in db.folds())
    X, y = [], []
    for x in res:
        X += x[0]
        y += x[1]
    return np.array(X), np.array(y)

def get_test_data(db, layer, n_jobs=1):
    features_dir = os.path.join(db.local_path, "features")
    def get_label(l):
        X, y = [], []
        for item in db.eval().filter(scene_label=l):
            features_filename = get_features_filename(features_dir, item.filename)
            x = np.load(features_filename)["layer"+str(layer)]
            X.append(x)
            y.append(l)
        return X, y
    res = Parallel(n_jobs=n_jobs)(delayed(get_label)(l) for l in db.scene_labels())
    X, y = [], []
    for x in res:
        X += x[0]
        y += x[1]
    return np.array(X), np.array(y)