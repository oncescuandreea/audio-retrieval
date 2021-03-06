import copy
import itertools
from pathlib import Path
from typing import Dict, List, Union

from base.base_dataset import BaseDataset
from typeguard import typechecked
from utils import memory_summary
from zsvision.zs_utils import concat_features, memcache


class CLOTHO(BaseDataset):

    @staticmethod
    @typechecked
    def dataset_paths(training_file=None) -> Dict[str, Union[str, List[str], Path, Dict]]:
        subset_paths = {}
        test_splits = {
            "val": "val_list.txt",
            "test": "test_list.txt",
        }
        for split_name, fname in test_splits.items():
            subset_paths[split_name] = {"train": "train_list.txt", "val": fname}

        feature_names = BaseDataset.common_feat_names()
        feature_names.append("audio.vggish.0")
        text_feat_paths = BaseDataset.common_text_feat_paths()
        text_feat_paths = {key: Path("text_embeddings") / fname
                           for key, fname in text_feat_paths.items()}
        challenge_text_feat_paths = {key: f"text_embeddings/{key}.pkl"
                                     for key in text_feat_paths}
        custom_paths = {
            "audio": ["aggregated_audio/vggish-raw.hickle"],
            "pann": ["aggregated_pann/pann-raw.hickle"],
            "syncnet": ["aggregated_syncnet/syncnet-raw.hickle"],
            "vggsound": ["aggregated_vggsound/vggsound-raw.hickle"],
            # "vggsound": ["aggregated_vggsound/vggsound-avg.pickle"],
            "speech": ["aggregated_speech/w2v_mean.pkl"]
        }
        feature_info = {
            "custom_paths": custom_paths,
            "feature_names": feature_names,
            "subset_list_paths": subset_paths,
            "text_feat_paths": text_feat_paths,
            "challenge_text_feat_paths": challenge_text_feat_paths,
            "raw_captions_path": "structured-symlinks/raw-captions.pkl",
        }
        return feature_info

    def load_features(self):
        root_feat = self.root_feat
        feat_names = {key: self.visual_feat_paths(key) for key in
                      self.paths["feature_names"]}
        feat_names.update(self.paths["custom_paths"])
        features = {}
        for expert, rel_names in feat_names.items():
            if expert not in self.ordered_experts:
                continue
            feat_paths = tuple([Path(root_feat) / rel_name for rel_name in rel_names])
            if len(feat_paths) == 1:
                features[expert] = memcache(feat_paths[0])
            else:
                # support multiple forms of feature (e.g. max and avg pooling). For
                # now, we only support direct concatenation
                msg = f"{expert}: Only direct concatenation of muliple feats is possible"
                print(f"Concatenating aggregates for {expert}....")
                assert self.feat_aggregation[expert]["aggregate"] == "concat", msg
                axis = self.feat_aggregation[expert]["aggregate-axis"]
                x = concat_features.cache_info()  # pylint: disable=no-value-for-parameter
                print(f"concat cache info: {x}")
                features_ = concat_features(feat_paths, axis=axis)
                memory_summary()

                # if expert == "speech":
                #     features_defaults = defaultdict(lambda: np.zeros((1, 300)))
                #     features_defaults.update(features_)
                #     features_ = features_defaults
                # Make separate feature copies for each split to allow in-place filtering
                features[expert] = copy.deepcopy(features_)

        self.features = features
        if self.challenge_mode:
            self.load_challenge_text_features()
        else:
            self.raw_captions = memcache(root_feat / self.paths["raw_captions_path"])
            # keys = list(raw_captions.keys())
            # raw_captions_fused = {}
            # for key in keys:
            #     raw_captions_fused[key] = list(itertools.chain.from_iterable(raw_captions[key]))
            # self.raw_captions = raw_captions_fused
            text_feat_path = root_feat / self.paths["text_feat_paths"][self.text_feat]
            self.text_features = memcache(text_feat_path)

        # overload video paths, which are structured differently for YouCook2
        self.video_path_retrieval = [f"videos/{x}.mp4"
                                     for x in self.partition_lists["val"]]

    def sanity_checks(self):
        msg = (f"Expected to have single test caption for AudioCaps, since we assume"
               f"that the captions are fused (but using {self.num_test_captions})")
        if self.fuse_captions is True:
            assert self.num_test_captions == 1, msg
