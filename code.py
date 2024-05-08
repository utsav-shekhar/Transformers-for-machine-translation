# -*- coding: utf-8 -*-
"""code.ipynb

Automatically generated by Colaboratory.

Original file is located at
    https://colab.research.google.com/drive/1uiMgHohtrPcEcPbgJeCXZJB0KEpv-rWE
"""

import torch
import torch.nn as nn
import torch.optim as optim
import numpy as np
import torch
import pandas as pd
!python -m spacy download fr_core_news_sm
import spacy
import torch
import torch.nn as nn
import torch.optim as optim
import numpy as np
nlp = spacy.load('fr_core_news_sm')

eng_file_path = 'train.en'
fr_file_path = 'train.fr'
with open(eng_file_path, 'r', encoding='utf-8') as file:
    eng_lines = file.readlines()

with open(fr_file_path, 'r', encoding='utf-8') as file:
    fr_lines = file.readlines()

eng_df = pd.DataFrame({'text': eng_lines})
fr_df = pd.DataFrame({'text': fr_lines})

def tokenize_text(text):
    tokens = text.strip().split()
    return tokens

eng_df['tokens'] = eng_df['text'].apply(tokenize_text)
fr_df['tokens'] = fr_df['text'].apply(tokenize_text)

eng_vocab = {}
fr_vocab = {}

for tokens in eng_df['tokens']:
    for token in tokens:
        if token not in eng_vocab:
            eng_vocab[token] = len(eng_vocab)

for tokens in fr_df['tokens']:
    for token in tokens:
        if token not in fr_vocab:
            fr_vocab[token] = len(fr_vocab)

eng_vocab['<UNK>'] = len(eng_vocab)
fr_vocab['<UNK>'] = len(fr_vocab)
fr_vocab['<sos>'] = len(fr_vocab)
fr_vocab['<eos>'] = len(fr_vocab)

max_seq_length = 50


def data_to_tensors(data, vocab, max_seq_length):
    tensors = []
    for tokens in data['tokens']:
        indices = [vocab.get(token, vocab['<UNK>']) for token in tokens]
        indices = indices[:max_seq_length]
        padding = [0] * (max_seq_length - len(indices))
        indices += padding
        tensors.append(torch.tensor(indices))

        # Check for out-of-bounds and padding values
        out_of_bounds = [idx for idx in indices if idx < 0 or idx >= len(vocab)]
        if out_of_bounds:
            print("Out-of-bounds indices:", out_of_bounds)

    return torch.stack(tensors)

def data_to_tensors2(data, vocab, max_seq_length):
    tensors = []
    for tokens in data['tokens']:
        indices = [vocab.get(token, vocab['<UNK>']) for token in tokens]
        indices = indices[:max_seq_length-1]
        padding = [0] * (max_seq_length - len(indices))
        indices += padding
        tensors.append(torch.tensor(indices))

        out_of_bounds = [idx for idx in indices if idx < 0 or idx >= len(vocab)]
        if out_of_bounds:
            print("Out-of-bounds indices:", out_of_bounds)

    return torch.stack(tensors)

src = data_to_tensors(eng_df, eng_vocab, max_seq_length)
tgt = data_to_tensors(fr_df, fr_vocab, max_seq_length)

print(src.shape)
print(tgt.shape)

print("Sample tgt tensor:", tgt[0])

max_value = torch.max(tgt)
min_value = torch.min(tgt)
if max_value >= len(fr_vocab) or min_value < 0:
    print("Target tensor contains values outside the range [0, tgt_vocab_size).")
    print("Max value:", max_value)
    print("Min value:", min_value)

len(fr_vocab)

"""Model architecture[From scratch]"""


d_model = 512
num_heads = 8
num_layers = 2
src_vocab_size = len(eng_vocab)
tgt_vocab_size = len(fr_vocab)
max_seq_length = 50
batch_size = 32

class PositionalEncoding(nn.Module):
    def __init__(self, d_model, max_seq_length):
        super(PositionalEncoding, self).__init__()
        position = torch.arange(0, max_seq_length, dtype=torch.float).unsqueeze(1)
        div_term = torch.exp(torch.arange(0, d_model, 2).float() * (-np.log(10000.0) / d_model))
        pe = torch.zeros(max_seq_length, d_model)
        pe[:, 0::2] = torch.sin(position * div_term)
        pe[:, 1::2] = torch.cos(position * div_term)
        pe = pe.unsqueeze(0).transpose(0, 1)
        self.register_buffer('pe', pe)

    def forward(self, x):
        return x + self.pe[:x.size(0), :]

class MultiHeadAttention(nn.Module):
    def __init__(self, d_model, num_heads):
        super(MultiHeadAttention, self).__init__()
        self.num_heads = num_heads
        self.d_model = d_model
        self.depth = d_model // num_heads
        self.WQ = nn.Linear(d_model, d_model)
        self.WK = nn.Linear(d_model, d_model)
        self.WV = nn.Linear(d_model, d_model)
        self.fc = nn.Linear(d_model, d_model)

    def split_heads(self, x, batch_size):
        x = x.view(batch_size, -1, self.num_heads, self.depth)
        return x.transpose(1, 2)

    def forward(self, query, key, value, mask):
        batch_size = query.size(0)
        Q = self.split_heads(self.WQ(query), batch_size)
        K = self.split_heads(self.WK(key), batch_size)
        V = self.split_heads(self.WV(value), batch_size)

        scores = torch.matmul(Q, K.transpose(-2, -1)) / (self.depth ** 0.5)
        if mask is not None:
            scores = scores.masked_fill(mask == 0, -1e9)
        attention = torch.nn.functional.softmax(scores, dim=-1)
        output = torch.matmul(attention, V)
        output = output.transpose(1, 2).contiguous().view(batch_size, -1, self.num_heads * self.depth)
        return self.fc(output)

class PositionwiseFeedForward(nn.Module):
    def __init__(self, d_model, d_ff):
        super(PositionwiseFeedForward, self).__init__()
        self.fc1 = nn.Linear(d_model, d_ff)
        self.fc2 = nn.Linear(d_ff, d_model)

    def forward(self, x):
        return self.fc2(torch.relu(self.fc1(x)))

# Encoder Layer
class EncoderLayer(nn.Module):
    def __init__(self, d_model, num_heads, d_ff):
        super(EncoderLayer, self).__init__()
        self.multi_head_attention = MultiHeadAttention(d_model, num_heads)
        self.feed_forward = PositionwiseFeedForward(d_model, d_ff)

    def forward(self, x, mask):
        attn_output = self.multi_head_attention(x, x, x, mask)
        x = x + attn_output
        ff_output = self.feed_forward(x)
        x = x + ff_output
        return x

# Decoder Layer
class DecoderLayer(nn.Module):
    def __init__(self, d_model, num_heads, d_ff):
        super(DecoderLayer, self).__init__()
        self.masked_multi_head_attention = MultiHeadAttention(d_model, num_heads)
        self.encoder_decoder_attention = MultiHeadAttention(d_model, num_heads)
        self.feed_forward = PositionwiseFeedForward(d_model, d_ff)

    def forward(self, x, enc_output, self_mask, enc_mask):
        masked_attn_output = self.masked_multi_head_attention(x, x, x, self_mask)
        x = x + masked_attn_output
        enc_dec_attn_output = self.encoder_decoder_attention(x, enc_output, enc_output, enc_mask)
        x = x + enc_dec_attn_output
        ff_output = self.feed_forward(x)
        x = x + ff_output
        return x

# Encoder
class Encoder(nn.Module):
    def __init__(self, d_model, num_heads, d_ff, num_layers, vocab_size, max_seq_length):
        super(Encoder, self).__init__()
        self.embedding = nn.Embedding(vocab_size, d_model)
        self.pe = PositionalEncoding(d_model, max_seq_length)
        self.layers = nn.ModuleList([EncoderLayer(d_model, num_heads, d_ff) for _ in range(num_layers)])

    def forward(self, x, mask):
        x = self.embedding(x)
        x = self.pe(x)
        for layer in self.layers:
            x = layer(x, mask)
        return x

# Decoder
class Decoder(nn.Module):
    def __init__(self, d_model, num_heads, d_ff, num_layers, vocab_size, max_seq_length):
        super(Decoder, self).__init__()  # Correct the missing parentheses here
        self.embedding = nn.Embedding(vocab_size, d_model)
        self.pe = PositionalEncoding(d_model, max_seq_length)
        self.layers = nn.ModuleList([DecoderLayer(d_model, num_heads, d_ff) for _ in range(num_layers)])
        self.lini = nn.Linear(d_model, 53791)

    def forward(self, x, enc_output, self_mask, enc_mask):
        x = self.embedding(x)
        x = self.pe(x)
        for layer in self.layers:
            x = layer(x, enc_output, self_mask, enc_mask)
        x = self.lini(x)
        return x


encoder = Encoder(d_model, num_heads, d_model * 4, num_layers, src_vocab_size, max_seq_length)
decoder = Decoder(d_model, num_heads, d_model * 4, num_layers, tgt_vocab_size, max_seq_length)

# Loss and optimizer
criterion = nn.CrossEntropyLoss()
encoder_optimizer = optim.Adam(encoder.parameters(), lr=0.001)
decoder_optimizer = optim.Adam(decoder.parameters(), lr=0.001)

def train_step(src, tgt):
    encoder_optimizer.zero_grad()
    decoder_optimizer.zero_grad()
    if tgt.dtype != torch.int64:
        print("Target tensor has an incorrect data type:", tgt.dtype)
        return 0  # Return a loss of 0

    src = src.to(device)
    tgt = tgt.to(device)


    src_mask = (src == 0).unsqueeze(1).unsqueeze(2)
    enc_output = encoder(src, src_mask)

    tgt_input = tgt
    tgt_mask = (tgt_input == 0).unsqueeze(1).unsqueeze(2)
    dec_output = decoder(tgt_input, enc_output, tgt_mask, src_mask)

    max_indices = torch.argmax(dec_output, dim=-1)

    # Print the input and the indices of the most probable words
    # print("Input Indices (src):", src)
    # print("Max Probability Indices (Decoded):", max_indices)
    print(max_indices.shape)

    # Check the range of values in tgt
    max_value = torch.max(tgt)
    min_value = torch.min(tgt)
    if max_value >= tgt_vocab_size or min_value < 0:
        print("Target tensor contains values outside the range [0, tgt_vocab_size).")
        return 0  # Return a loss of 0

    loss = criterion(dec_output.transpose(1, 2), tgt)

    # Backpropagation
    loss.backward()
    encoder_optimizer.step()
    decoder_optimizer.step()

    return loss.item()

reference_translations = []
generated_translations = []

device = torch.device("cuda" if torch.cuda.is_available() else "cpu")

# Move model parameters to the GPU
encoder.to(device)
decoder.to(device)

reference_translations = []
generated_translations = []

device = torch.device("cuda" if torch.cuda.is_available() else "cpu")

encoder.to(device)
decoder.to(device)

from tqdm import tqdm

num_epochs = 3
for epoch in range(num_epochs):
    total_loss = 0
    reference_translations = []
    generated_translations = []

    for i in tqdm(range(0, len(src), batch_size), desc=f'Epoch [{epoch + 1}/{num_epochs}]'):
        batch_src = src[i:i + batch_size]
        batch_tgt = tgt[i:i + batch_size]
        # print("shape : = ",batch_src.shape)
        # print("shape : = ",batch_tgt.shape)
        loss = train_step(batch_src, batch_tgt)
        total_loss += loss


    print(f'Loss: {total_loss / len(src)}')

len(eng_vocab)

eng_df

import pandas as pd
from nltk.translate.bleu_score import sentence_bleu, SmoothingFunction


def collect_references_and_translations(eng_df, fr_df, encoder, decoder, eng_vocab, fr_vocab, max_seq_length):
    references = fr_df['text'].tolist()
    translations = []


    for eng_sentence in eng_df['text']:
        french_translation = translate_sentence_to_string(eng_sentence, encoder, decoder, eng_vocab, fr_vocab, max_seq_length)
        translations.append(french_translation)

    return translations, references


def calculate_bleu_scores_nltk(translations, references):
    smoothing = SmoothingFunction()
    individual_bleu_scores = []

    for translation, reference in zip(translations, references):
        bleu = sentence_bleu([reference.split()], translation.split(), smoothing_function=smoothing.method0)
        individual_bleu_scores.append(bleu)

    avg_bleu = sum(individual_bleu_scores) / len(individual_bleu_scores)
    return avg_bleu, individual_bleu_scores


train_translations, train_references = collect_references_and_translations(eng_df, fr_df, encoder, decoder, eng_vocab, fr_vocab, max_seq_length)

avg_train_bleu, individual_train_bleu_scores = calculate_bleu_scores_nltk(train_translations, train_references)

print("Average BLEU Score on Training Dataset:", avg_train_bleu)
print("Individual BLEU Scores for Training Sentences:", individual_train_bleu_scores)

eng_file_path = 'train.en'
fr_file_path = 'test.fr'

with open(eng_file_path, 'r', encoding='utf-8') as file:
    eng_lines = file.readlines()

with open(fr_file_path, 'r', encoding='utf-8') as file:
    fr_lines = file.readlines()


eng_df = pd.DataFrame({'text': eng_lines})
fr_df = pd.DataFrame({'text': fr_lines})


def tokenize_text(text):
    tokens = text.strip().split()
    return tokens


eng_df['tokens'] = eng_df['text'].apply(tokenize_text)
fr_df['tokens'] = fr_df['text'].apply(tokenize_text)

eng_vocab = {}
fr_vocab = {}

for tokens in eng_df['tokens']:
    for token in tokens:
        if token not in eng_vocab:
            eng_vocab[token] = len(eng_vocab)


for tokens in fr_df['tokens']:
    for token in tokens:
        if token not in fr_vocab:
            fr_vocab[token] = len(fr_vocab)


eng_vocab['<UNK>'] = len(eng_vocab)
fr_vocab['<UNK>'] = len(fr_vocab)
fr_vocab['<sos>'] = len(fr_vocab)
fr_vocab['<eos>'] = len(fr_vocab)

max_seq_length = 50

def data_to_tensors(data, vocab, max_seq_length):
    tensors = []
    for tokens in data['tokens']:
        indices = [vocab.get(token, vocab['<UNK>']) for token in tokens]
        indices = indices[:max_seq_length]
        padding = [0] * (max_seq_length - len(indices))
        indices += padding
        tensors.append(torch.tensor(indices))

        out_of_bounds = [idx for idx in indices if idx < 0 or idx >= len(vocab)]
        if out_of_bounds:
            print("Out-of-bounds indices:", out_of_bounds)

    return torch.stack(tensors)

def data_to_tensors2(data, vocab, max_seq_length):
    tensors = []
    for tokens in data['tokens']:
        indices = [vocab.get(token, vocab['<UNK>']) for token in tokens]
        indices = indices[:max_seq_length-1]
        padding = [0] * (max_seq_length - len(indices))
        indices += padding
        tensors.append(torch.tensor(indices))

        out_of_bounds = [idx for idx in indices if idx < 0 or idx >= len(vocab)]
        if out_of_bounds:
            print("Out-of-bounds indices:", out_of_bounds)

    return torch.stack(tensors)

src = data_to_tensors(eng_df, eng_vocab, max_seq_length)
tgt = data_to_tensors(fr_df, fr_vocab, max_seq_length)

print(src.shape)
print(tgt.shape)
# Print a sample target tensor for inspection
print("Sample tgt tensor:", tgt[0])

max_value = torch.max(tgt)
min_value = torch.min(tgt)
if max_value >= len(fr_vocab) or min_value < 0:
    print("Target tensor contains values outside the range [0, tgt_vocab_size).")
    print("Max value:", max_value)
    print("Min value:", min_value)

import matplotlib.pyplot as plt

# Loss values for each epoch
losses = [2.0319342, 1.7214201, 1.4012196, 1.4004181, 1.4002111, 1.4001823]

# Epoch numbers
epochs = [1, 2, 3, 4, 5, 6]

# Create a line plot
plt.plot(epochs, losses, marker='o', linestyle='-')
plt.title('Loss vs. Epoch')
plt.xlabel('Epoch')
plt.ylabel('Loss')
plt.grid(True)

# Display the plot
plt.show()
