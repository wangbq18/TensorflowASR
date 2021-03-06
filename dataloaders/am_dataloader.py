from utils.speech_featurizers import SpeechFeaturizer
from utils.text_featurizers import TextFeaturizer
import pypinyin
import numpy as np
from augmentations.augments import Augmentation
import random


class AM_DataLoader():

    def __init__(self, config_dict):
        self.speech_config = config_dict['speech_config']


        self.text_config = config_dict['decoder_config']
        self.augment_config = config_dict['augments_config']

        self.batch = config_dict['learning_config']['running_config']['batch_size']
        self.speech_featurizer = SpeechFeaturizer(self.speech_config)
        self.text_featurizer = TextFeaturizer(self.text_config)
        self.make_file_list(self.speech_config['train_list'])
        self.augment = Augmentation(self.augment_config)
        self.init_text_to_vocab()
        self.epochs = 1

        self.steps = 0
    def get_per_epoch_steps(self):
        return len(self.train_list)//self.batch
    def init_text_to_vocab(self):
        pypinyin.load_phrases_dict({'调大': [['tiáo'], ['dà']],
                                    '调小': [['tiáo'], ['xiǎo']],
                                    '调亮': [['tiáo'], ['liàng']],
                                    '调暗': [['tiáo'], ['àn']],
                                    '肖': [['xiāo']],
                                    '英雄传': [['yīng'], ['xióng'], ['zhuàn']],
                                    '新传': [['xīn'], ['zhuàn']],
                                    '外传': [['wài'], ['zhuàn']],
                                    '正传': [['zhèng'], ['zhuàn']], '水浒传': [['shuǐ'], ['hǔ'], ['zhuàn']]
                                    })

        def text_to_vocab_func(txt):
            return pypinyin.lazy_pinyin(txt, 1, errors='ignore')

        self.text_to_vocab = text_to_vocab_func

    def augment_data(self, wavs, label, label_length):
        if not self.augment.available():
            return None
        mels = []
        input_length = []
        label_ = []
        label_length_ = []
        wavs_ = []
        max_input = 0
        max_wav = 0
        for idx, wav in enumerate(wavs):

            data = self.augment.process(wav.flatten())
            speech_feature = self.speech_featurizer.extract(data)
            if speech_feature.shape[0] // self.speech_config['reduction_factor'] < label_length[idx]:
                continue
            max_input = max(max_input, speech_feature.shape[0])

            max_wav = max(max_wav, len(data))

            wavs_.append(data)

            mels.append(speech_feature)
            input_length.append(speech_feature.shape[0] // self.speech_config['reduction_factor'])
            label_.append(label[idx])
            label_length_.append(label_length[idx])

        for i in range(len(mels)):
            if mels[i].shape[0] < max_input:
                pad = np.ones([max_input - mels[i].shape[0], mels[i].shape[1],mels[i].shape[2]]) * mels[i].min()
                mels[i] = np.vstack((mels[i], pad))

        wavs_ = self.speech_featurizer.pad_signal(wavs_, max_wav)

        x = np.array(mels, 'float32')
        label_ = np.array(label_, 'int32')

        input_length = np.array(input_length, 'int32')
        label_length_ = np.array(label_length_, 'int32')

        wavs_ = np.array(np.expand_dims(wavs_, -1), 'float32')

        return x, wavs_, input_length, label_, label_length_

    def make_file_list(self, wav_list):
        with open(wav_list, encoding='utf-8') as f:
            data = f.readlines()
        num = len(data)
        self.train_list = data[:int(num * 0.99)]
        self.test_list = data[int(num * 0.99):]
        np.random.shuffle(self.train_list)
        self.pick_index = [0.] * len(self.train_list)

    def only_chinese(self, word):

        for ch in word:
            if '\u4e00' <= ch <= '\u9fff':
                pass
            else:
                return False

        return True

    def generator(self, train=True):

        if train:
            indexs = np.argsort(self.pick_index)[:2 * self.batch]
            indexs = random.sample(indexs.tolist(), self.batch)
            sample = [self.train_list[i] for i in indexs]
            for i in indexs:
                self.pick_index[int(i)] += 1
            self.epochs = int(np.mean(self.pick_index))
        else:
            sample = random.sample(self.test_list, self.batch)

        mels = []
        input_length = []

        y1 = []
        label_length1 = []

        wavs = []

        max_wav = 0
        max_input = 0
        max_label1 = 0
        for i in sample:
            wp, txt = i.strip().split('\t')
            wp=wp.replace(r'data_aishell\data_aishell','data_aishell')
            try:
                data = self.speech_featurizer.load_wav(wp)
            except:
                print('load data failed')
                continue
            if len(data) < 400:
                continue
            elif len(data) > self.speech_featurizer.sample_rate * 15:
                continue

            if not self.only_chinese(txt):
                continue
            speech_feature = self.speech_featurizer.extract(data)
            max_input = max(max_input, speech_feature.shape[0])

            py3 = self.text_to_vocab(txt)
            if len(py3) == 0:
                continue

            text_feature = self.text_featurizer.extract(py3)
            max_label1 = max(max_label1, len(text_feature))
            max_wav = max(max_wav, len(data))
            if speech_feature.shape[0] / self.speech_config['reduction_factor'] < len(text_feature):
                continue
            mels.append(speech_feature)
            wavs.append(data)
            input_length.append(speech_feature.shape[0] // self.speech_config['reduction_factor'])
            y1.append(np.array(text_feature))
            label_length1.append(len(text_feature))

        for i in range(len(mels)):
            if mels[i].shape[0] < max_input:
                pad = np.ones([max_input - mels[i].shape[0], mels[i].shape[1], mels[i].shape[2]]) * mels[i].min()
                mels[i] = np.vstack((mels[i], pad))

        wavs = self.speech_featurizer.pad_signal(wavs, max_wav)
        for i in range(len(y1)):
            if y1[i].shape[0] < max_label1:
                pad = np.ones(max_label1 - y1[i].shape[0])*self.text_featurizer.pad
                y1[i] = np.hstack((y1[i], pad))

        x = np.array(mels, 'float32')
        y1 = np.array(y1, 'int32')

        input_length = np.array(input_length, 'int32')
        label_length1 = np.array(label_length1, 'int32')

        wavs = np.array(np.expand_dims(wavs, -1), 'float32')

        return x, wavs, input_length, y1, label_length1


if __name__ == '__main__':
    from utils.user_config import UserConfig

    config = UserConfig(r'D:\TF2-ASR\config.yml')

    dg = AM_DataLoader(config)
    x, wavs, input_length, y1, label_length1 = dg.generator()
    print(x.shape, wavs.shape, input_length.shape, y1.shape, label_length1.shape)
