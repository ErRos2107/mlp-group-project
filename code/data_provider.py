# -*- coding: utf-8 -*-
"""Data providers.

This module provides classes for loading datasets and iterating over batches of
data points.
"""

import numpy as np
import os
import scipy.sparse as sp

from sklearn.model_selection import KFold
DEFAULT_SEED = 22012018


class DataProvider(object):
    """Generic data provider."""

    def __init__(self, inputs, targets, batch_size, max_num_batches=-1,
                 shuffle_order=True, rng=None):
        """Create a new data provider object.

        Args:
            inputs (ndarray): Array of data input features of shape
                (num_data, input_dim).
            targets (ndarray): Array of data output targets of shape
                (num_data, output_dim) or (num_data,) if output_dim == 1.
            batch_size (int): Number of data points to include in each batch.
            max_num_batches (int): Maximum number of batches to iterate over
                in an epoch. If `max_num_batches * batch_size > num_data` then
                only as many batches as the data can be split into will be
                used. If set to -1 all of the data will be used.
            shuffle_order (bool): Whether to randomly permute the order of
                the data before each epoch.
            rng (RandomState): A seeded random number generator.
        """
        self.inputs = inputs
        self.targets = targets
        if batch_size < 1:
            raise ValueError('batch_size must be >= 1')
        self._batch_size = batch_size
        if max_num_batches == 0 or max_num_batches < -1:
            raise ValueError('max_num_batches must be -1 or > 0')
        self._max_num_batches = max_num_batches
        self._update_num_batches()
        self.shuffle_order = shuffle_order
        self._current_order = np.arange(inputs.shape[0])
        if rng is None:
            rng = np.random.RandomState(DEFAULT_SEED)
        self.rng = rng
        self.new_epoch()

    @property
    def batch_size(self):
        """Number of data points to include in each batch."""
        return self._batch_size

    @batch_size.setter
    def batch_size(self, value):
        if value < 1:
            raise ValueError('batch_size must be >= 1')
        self._batch_size = value
        self._update_num_batches()

    @property
    def max_num_batches(self):
        """Maximum number of batches to iterate over in an epoch."""
        return self._max_num_batches

    @max_num_batches.setter
    def max_num_batches(self, value):
        if value == 0 or value < -1:
            raise ValueError('max_num_batches must be -1 or > 0')
        self._max_num_batches = value
        self._update_num_batches()

    def _update_num_batches(self):
        """Updates number of batches to iterate over."""
        # maximum possible number of batches is equal to number of whole times
        # batch_size divides in to the number of data points which can be
        # found using integer division
        possible_num_batches = self.inputs.shape[0] // self.batch_size
        if self.max_num_batches == -1:
            self.num_batches = possible_num_batches
        else:
            self.num_batches = min(self.max_num_batches, possible_num_batches)

    def __iter__(self):
        """Implements Python iterator interface.

        This should return an object implementing a `next` method which steps
        through a sequence returning one element at a time and raising
        `StopIteration` when at the end of the sequence. Here the object
        returned is the DataProvider itself.
        """
        return self

    def new_epoch(self):
        """Starts a new epoch (pass through data), possibly shuffling first."""
        self._curr_batch = 0
        if self.shuffle_order:
            self.shuffle()

    def __next__(self):
        return self.next()

    def reset(self):
        """Resets the provider to the initial state."""
        inv_perm = np.argsort(self._current_order)
        self._current_order = self._current_order[inv_perm]
        self.inputs = self.inputs[inv_perm]
        self.targets = self.targets[inv_perm]
        self.new_epoch()

    def shuffle(self):
        """Randomly shuffles order of data."""
        perm = self.rng.permutation(self.inputs.shape[0])
        self._current_order = self._current_order[perm]
        self.inputs = self.inputs[perm]
        self.targets = self.targets[perm]

    def next(self):
        """Returns next data batch or raises `StopIteration` if at end."""
        if self._curr_batch + 1 > self.num_batches:
            # no more batches in current iteration through data set so start
            # new epoch ready for another pass and indicate iteration is at end
            self.new_epoch()
            raise StopIteration()
        # create an index slice corresponding to current batch number
        batch_slice = slice(self._curr_batch * self.batch_size,
                            (self._curr_batch + 1) * self.batch_size)
        inputs_batch = self.inputs[batch_slice]
        targets_batch = self.targets[batch_slice]
        self._curr_batch += 1
        return inputs_batch, targets_batch


class ASSISTDataProvider(DataProvider):
    """Data provider for ASSISTments 2009/2015 student assessment data set."""

    def __init__(
            self,
            data_dir,
            which_set='train',
            which_year='09',
            fraction=1,
            use_plus_minus_feats=False,
            use_compressed_sensing=False,
            batch_size=100,
            max_num_batches=-1,
            shuffle_order=True,
            rng=None,
            data=None):
        """Create a new ASSISTments data provider object.

        Args:
            which_set: One of 'train' or 'test'. Determines which
                portion of the ASSIST data this object should provide.
            which_year: either '09' or '15'. Determines which dataset to use.
            fraction (float): fraction of dataset to use.
            use_plus_minus_feats (boolean): if True, use a different encoding
                of the final dimension of inputs. This new encoding
                uses a +/-1 hot vector of size max_prob_set_id + 1, instead
                of a 1 hot vector of size 2*max_prob_set_id + 1.
            batch_size (int): Number of data points to include in each batch.
            max_num_batches (int): Maximum number of batches to iterate over
                in an epoch. If `max_num_batches * batch_size > num_data` then
                only as many batches as the data can be split into will be
                used. If set to -1 all of the data will be used.
            shuffle_order (bool): Whether to randomly permute the order of
                the data before each epoch.
            rng (RandomState): A seeded random number generator.
            data: (inputs, target): if not None, use this data instead of
                loading from file
        """
        expanded_data_dir = os.path.expanduser(data_dir)
        data_path = os.path.join(
            expanded_data_dir, 'assist{0}-{1}'.format(which_year, which_set))
        self._validate_inputs(which_set, which_year, data_path)
        self.which_set = which_set
        self.which_year = which_year
        self.data_dir = expanded_data_dir
        self.num_classes = 2
        self.fraction = fraction
        self.use_plus_minus_feats = use_plus_minus_feats
        self.use_compressed_sensing = use_compressed_sensing

        if data:
            inputs, targets, self.target_ids = data['inputs'], \
                data['targets'], data['target_ids']
            self.max_num_ans, self.max_prob_set_id = data['max_num_ans'],\
                data['max_prob_set_id']
            self.encoding_dim = data['encoding_dim']
        else:
            inputs, targets = self.load_data(data_path, use_plus_minus_feats)
            inputs, targets = self.reduce_data(inputs, targets, fraction)
            if use_compressed_sensing:
                inputs = self.apply_compressed_sensing(inputs, rng)
        # pass the loaded data to the parent class __init__
        super(ASSISTDataProvider, self).__init__(
            inputs, targets, batch_size, max_num_batches, shuffle_order, rng)

    def apply_compressed_sensing(self, inputs, rng):
        """Map input features (of length 'encoding_dim') down to a randomly generated
        vector sampled from a standard gaussian in a lower dimensional space. If this
        is test time, load training matrix from file. If train time, make the matrix.
        """
        print('using compressed sensing!')
        train_path = os.path.join(
            self.data_dir, 'assist{0}-{1}'.format(self.which_year, 'train'))

        if self.which_set == 'test':
            loaded = np.load(train_path + '-compression-matrix.npz')
            self.compress_matrix = loaded['compress_matrix']
            self.compress_dim = self.compress_matrix.shape[1]
        elif self.which_set == 'train':
            self.compress_matrix = self.make_compression_matrix(train_path, rng)

        inputs = self.compress_inputs(inputs)
        return inputs

    def make_compression_matrix(self, train_path, rng):
        """Create matrix for mapping input features (of length 'encoding_dim') to
        lower dimensional gaussian vector
        """
        self.compress_dim = 100  # value used in original DKT paper
        if rng:
            compress_matrix = rng.randn(self.encoding_dim, self.compress_dim)
        else:
            compress_matrix = np.random.randn(self.encoding_dim, self.compress_dim)

        np.savez(train_path + '-compression-matrix', compress_matrix=compress_matrix)
        return compress_matrix

    def compress_inputs(self, inputs):
        """Apply compression matrix to inputs"""
        num_students = inputs.shape[0]
        inputs = inputs.toarray()
        inputs = np.dot(inputs.reshape(-1, self.encoding_dim), self.compress_matrix)
        self.encoding_dim = self.compress_dim

        return sp.csr_matrix(inputs.reshape(num_students, -1))

    def reduce_data(self, inputs, targets, fraction):
        num_data = int(inputs.shape[0] * fraction)
        inputs = inputs[:num_data]
        targets = targets[:num_data]
        self.target_ids = self.target_ids[:num_data]
        return inputs, targets

    def load_data(self, data_path, use_plus_minus_feats):
        """ Load data from files, optionally reducing and/or compressing"""
        loaded = np.load(data_path + '-targets.npz')
        self.max_num_ans = int(loaded['max_num_ans'])
        self.max_prob_set_id = int(loaded['max_prob_set_id'])
        targets = loaded['targets']
        if use_plus_minus_feats:
            print("using plus minus feats!!!")
            inputs = sp.load_npz(data_path + '-inputs-plus-minus.npz')
            self.encoding_dim = self.max_prob_set_id + 1
        else:
            inputs = sp.load_npz(data_path + '-inputs.npz')
            self.encoding_dim = 2 * self.max_prob_set_id + 1
        self.target_ids = sp.load_npz(data_path + '-targetids.npz')

        return inputs, targets

    def next(self):
        """Returns next data batch or raises `StopIteration` if at end."""
        if self._curr_batch + 1 > self.num_batches:
            # no more batches in current iteration through data set so start
            # new epoch ready for another pass and indicate iteration is at end
            self.new_epoch()
            raise StopIteration()
        # create an index slice corresponding to current batch number
        batch_slice = slice(self._curr_batch * self.batch_size,
                            (self._curr_batch + 1) * self.batch_size)
        inputs_batch = self.inputs[batch_slice]
        targets_batch = self.targets[batch_slice]
        # target_ids_global = self.target_ids[batch_slice]
        target_ids_batch = self.target_ids[batch_slice]
        self._curr_batch += 1

        batch_inputs, batch_target_ids, batch_targets = \
            self.transform_batch(inputs_batch, target_ids_batch, targets_batch)

        return batch_inputs, batch_targets, batch_target_ids

    def transform_batch(self, inputs_batch, target_ids_batch, targets_batch):
        """reshape batch of data ready to be processed by an RNN"""
        # extract one-hot encoded feature vectors and reshape them
        # so we can feed them to the RNN
        batch_inputs = inputs_batch.toarray()
        batch_inputs = batch_inputs.reshape(
            self.batch_size, self.max_num_ans, self.encoding_dim)
        # targets_batch is a list of lists, which we need to flatten
        batch_targets = [i for sublist in targets_batch for i in sublist]
        batch_targets = np.array(batch_targets, dtype=np.float32)
        # during learning, the data for each student in a batch gets shuffled together
        # hence, we need a vector of indices to locate their predictions after learning
        batch_target_ids = target_ids_batch.toarray()
        batch_target_ids = np.array(
            batch_target_ids.reshape(-1),
            dtype=np.int32)

        return batch_inputs, batch_target_ids, batch_targets

    def reset(self):
        """Resets the provider to the initial state."""
        inv_perm = np.argsort(self._current_order)
        self._current_order = self._current_order[inv_perm]
        self.inputs = self.inputs[inv_perm]
        self.targets = self.targets[inv_perm]
        self.target_ids = self.target_ids[inv_perm]
        self.new_epoch()

    def shuffle(self):
        """Randomly shuffles order of data."""
        perm = self.rng.permutation(self.inputs.shape[0])
        self._current_order = self._current_order[perm]
        self.inputs = self.inputs[perm]
        self.targets = self.targets[perm]
        self.target_ids = self.target_ids[perm]

    def _get_k_folds(self, k, threshold=None):
        """ Returns k pairs of DataProviders: (train_data_provider, val_data_provider)
        where the data split in each tuple is determined by k-fold cross val."""

        assert self.which_set == 'train', (
            'Expected which_set to be train. '
            'Got {}'.format(self.which_set)
        )
        inputs = self.inputs
        targets = self.targets
        target_ids = self.target_ids

        kf = KFold(n_splits=k)
        # init list of DPs
        for train_index, val_index in kf.split(inputs):
            inputs_train, inputs_val = inputs[train_index], inputs[val_index]
            targets_train, targets_val = targets[train_index], targets[val_index]
            target_ids_train, targets_ids_val = target_ids[train_index], target_ids[val_index]

            if threshold:
                # break up a student's sequence (into threshold-sized chunks)
                # *after* the train/val split since if we did it beforehand then the same
                # students' data might be split across the two sets, which would make the
                # validation set a bad proxy for the test set.
                inputs_train, target_ids_train, targets_train, threshold = \
                    self.truncate_sequences(inputs_train, target_ids_train,
                                            targets_train, threshold)
                inputs_val, targets_ids_val, targets_val, threshold = \
                    self.truncate_sequences(inputs_val, targets_ids_val,
                                            targets_val, threshold)
            else:
                threshold = self.max_num_ans
                
            train_data = {
                'inputs': inputs_train,
                'targets': targets_train,
                'target_ids': target_ids_train,
                'max_num_ans': threshold,
                'max_prob_set_id': self.max_prob_set_id,
                'encoding_dim': self.encoding_dim}
            val_data = {
                'inputs': inputs_val,
                'targets': targets_val,
                'target_ids': targets_ids_val,
                'max_num_ans': threshold,
                'max_prob_set_id': self.max_prob_set_id,
                'encoding_dim': self.encoding_dim}

            train_dp = ASSISTDataProvider(
                data_dir=self.data_dir,
                which_set=self.which_set,
                which_year=self.which_year,
                fraction=self.fraction,
                use_plus_minus_feats=self.use_plus_minus_feats,
                use_compressed_sensing=self.use_compressed_sensing,
                batch_size=self.batch_size,
                max_num_batches=self.max_num_batches,
                shuffle_order=self.shuffle_order,
                rng=self.rng,
                data=train_data)
            val_dp = ASSISTDataProvider(
                data_dir=self.data_dir,
                which_set=self.which_set,
                which_year=self.which_year,
                fraction=self.fraction,
                use_plus_minus_feats=self.use_plus_minus_feats,
                use_compressed_sensing=self.use_compressed_sensing,
                batch_size=self.batch_size,
                max_num_batches=self.max_num_batches,
                shuffle_order=self.shuffle_order,
                rng=self.rng,
                data=val_data)
            yield (train_dp, val_dp)

    def train_validation_split(self, threshold=None):
        """Return 2 data providers with 80/20 data split

        Note, we break up a student's sequence (into threshold-sized chunks)
        *after* the train/val split since if we did it beforehand then the same
        students' data might be split across the two sets, which would make the
        validation set a bad proxy for the test set"""
        for train, validation in self._get_k_folds(5, threshold):
            train_provider = train
            validation_provider = validation
            break
        return train_provider, validation_provider

    def truncate_sequences(self, inputs, target_ids, targets, threshold):
        """Split the data of each student into threshold*encoding_dim chunks.

        Rather than use the default max_num_ans*encoding_dim vector that contains all the
        (padded) data for that student, we break up a student's data into chunks. Each new chunk is
        effectively treated as a new student. Note that since we have already right-padded
        student's data with zeros, some of these new chunks will be all zero, and can thus
        be discarded."""
        threshold = min(self.max_num_ans, threshold)
        inputs = self._truncate_inputs_or_ids(inputs,
                                              self.encoding_dim,
                                              threshold)
        target_ids = self._truncate_inputs_or_ids(target_ids,
                                                  self.max_prob_set_id,
                                                  threshold)
        targets = self._truncate_targets(targets, threshold)
        print('Number of effective students is now {}.'.format(inputs.shape[0]))

        return inputs, target_ids, targets, threshold

    def _truncate_targets(self, targets, threshold):
        new_targets = []
        for student in targets:
            for i in range(0, len(student), threshold):
                new_targets.append(student[i:i + threshold])
        return np.array(new_targets)

    def _truncate_inputs_or_ids(self, input_or_id, final_dim, threshold):

        # don't truncate all the input_or_ids in one-go due to memory overload.
        # do it in steps of 1000 students and concatenate afterwards
        list_of_truncated_seqs = []
        for i in range(0, input_or_id.shape[0], 1000):
            x = input_or_id[i:i+1000].toarray()
            x = x.reshape(x.shape[0],
                          self.max_num_ans,
                          final_dim)

            # We want to break the data into threshold-sized chunks,
            # so right-pad with zeros to ensure divisibility
            pad_size = threshold - self.max_num_ans % threshold
            pad = ((0, 0), (0, pad_size), (0, 0))
            x = np.pad(x, pad_width=pad, mode='constant', constant_values=0)

            # break up data into threshold-sized chunks
            new_x = x.reshape(-1, threshold, final_dim)

            # Only keep those chunks that are non-zero
            non_empty_mask = np.max((new_x != np.zeros((threshold, final_dim))),
                                    axis=(1, 2))
            num_effective_students = np.sum(non_empty_mask)
            non_empty_indices = np.nonzero(non_empty_mask)
            new_x = new_x[non_empty_indices]
            list_of_truncated_seqs.append(
                sp.csr_matrix(new_x.reshape(num_effective_students, -1)))

        return sp.vstack(list_of_truncated_seqs)

    def _validate_inputs(self, which_set, which_year, data_path):
        assert which_set in ['train', 'test'], (
            'Expected which_set to be either train or test. '
            'Got {0}'.format(which_set)
        )
        assert which_year in ['09', '15'], (
            'Expected which_year to be either 09 or 15. '
            'Got {}.format(which_year'
        )
        assert os.path.isfile(data_path + '-inputs.npz'), (
                'Data file does not exist at expected path: ' + data_path
        )
        assert os.path.isfile(data_path + '-targets.npz'), (
                'Data file does not exist at expected path: ' + data_path
        )
