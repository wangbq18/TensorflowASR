from utils.text_featurizers import TextFeaturizer
import pypinyin
import numpy as np
from keras.preprocessing.sequence import pad_sequences
from keras_bert import Tokenizer, load_vocabulary, load_trained_model_from_checkpoint
import random

class LM_DataLoader():
    def __init__(self, config):
        self.init_all(config)
        self.vocab_featurizer = TextFeaturizer(config['lm_vocab'])
        self.word_featurizer = TextFeaturizer(config['lm_word'])
        self.init_text_to_vocab()
        self.batch = config['running_config']['batch_size']

    def init_bert(self, config, checkpoint):
        model = load_trained_model_from_checkpoint(config, checkpoint, trainable=False, seq_len=None)
        return model
    def get_per_epoch_steps(self):
        return len(self.train_texts)//self.batch
    def init_all(self, config):
        bert_config = config['bert']['config_json']
        bert_checkpoint =config['bert']['bert_ckpt']
        bert_vocab =config['bert']['bert_vocab']
        bert_vocabs = load_vocabulary(bert_vocab)
        self.bert_token = Tokenizer(bert_vocabs)
        self.bert = self.init_bert(bert_config, bert_checkpoint)
        self.train_texts,self.test_texts = self.get_sentence(config['train_list'])
        self.train_pick=[0]*len(self.train_texts)
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

    def get_sentence(self, data_path):
        from tqdm import tqdm
        with open(data_path, encoding='utf-8') as f:
            data = f.readlines()

        txts = []
        for txt in tqdm(data):
            txt = txt.strip()
            if len(txt) > 150:
                continue
            txts.append(txt)
        num=len(txts)
        train=txts[:int(num*0.99)]
        test=txts[int(num*0.99):]
        return train,test

    def preprocess(self, tokens, txts):
        x = []
        y = []
        for token, txt in zip(tokens, txts):
            # print(py,txt)
            # try:
            x_ = [self.vocab_featurizer.startid()]
            y_ = [self.word_featurizer.startid()]
            for i in token:
                x_.append(self.vocab_featurizer.token_to_index[i])
            for i in txt:
                y_.append(self.word_featurizer.token_to_index[i])
            x_.append(self.vocab_featurizer.endid())
            y_.append(self.word_featurizer.endid())
            x.append(np.array(x_))
            y.append(np.array(y_))

        return x, y

    def bert_decode(self, x, x2=None):
        tokens, segs = [], []
        if x2 is not None:
            for i, j in zip(x, x2):
                t, s = self.bert_token.encode(''.join(i))
                index = np.where(j == 2)[0]
                if len(index) > 0:
                    for n in index:
                        t[int(n)] = 103
                tokens.append(t)
                segs.append(s)
        else:
            for i in x:
                t, s = self.bert_token.encode(''.join(i))
                tokens.append(t)
                segs.append(s)
        return tokens, segs

    def pad(self, x, mode=1):
        length = 0

        for i in x:
            length = max(length, len(i))
        if mode == 2:
            for i in range(len(x)):
                pading = np.ones([length - len(x[i]), x[i].shape[1]]) * -10.
                x[i] = np.vstack((x[i], pading))

        else:
            x = pad_sequences(x, length, padding='post', truncating='post')
        return x

    def get_bert_feature(self, bert_t, bert_s):
        f = []
        for t, s in zip(bert_t, bert_s):
            t = np.expand_dims(np.array(t), 0)
            s = np.expand_dims(np.array(s), 0)
            feature = self.bert.predict([t, s])
            f.append(feature[0])
        return f

    def generate(self,train=True):
        if train:
            indexs = np.argsort(self.train_pick)[:2 * self.batch]
            indexs = random.sample(indexs.tolist(), self.batch)
            sample = [self.train_texts[i] for i in indexs]
            for i in indexs:
                self.train_pick[int(i)] += 1
            self.epochs = int(np.mean(self.train_pick))
        else:
            sample = random.sample(self.test_texts, self.batch)
        trainx = [self.text_to_vocab(i) for i in sample]
        trainy = sample
        x, y = self.preprocess(trainx, trainy)
        e_bert_t, e_bert_s = self.bert_decode(trainy)
        e_features = self.get_bert_feature(e_bert_t, e_bert_s)
        x = self.pad(x)
        y = self.pad(y)
        e_features = self.pad(e_features, 2)

        x = np.array(x)
        y = np.array(y)
        e_features = np.array(e_features, dtype='float32')

        return x, y, e_features


if __name__ == '__main__':
    from utils.user_config import UserConfig

    config = UserConfig(r'D:\TF2-ASR\configs\lm_data.yml', r'D:\TF2-ASR\configs\transformer.yml')

    dg = LM_DataLoader(config)
    x, y, features= dg.generate()
    print(x.shape,y.shape,features.shape)
