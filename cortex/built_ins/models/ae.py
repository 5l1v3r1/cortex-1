'''Simple Variational Autoencoder model.
'''

from cortex.plugins import register_plugin, ModelPlugin
import torch
import torch.nn as nn
import torch.nn.functional as F
from torch.autograd import Variable
from cortex.main import run
from cortex.built_ins.models.utils import update_encoder_args, update_decoder_args, ms_ssim


__author__ = 'R Devon Hjelm and Samuel Lavoie'
__author_email__ = 'erroneus@gmail.com'


class AENetwork(nn.Module):
    '''AE model.

    Attributes:
        encoder: Encoder network.
        mu_net: Single layer network for caculating mean.
        logvar_net: Single layer network for calculating log variance.
        decoder: Decoder network.
        mu: The mean after encoding.
        logvar: The log variance after encoding.
        latent: The latent state (Z).

    '''

    def __init__(self, encoder, decoder, dim_out=None, dim_z=None):
        super(AENetwork, self).__init__()
        self.encoder = encoder
        self.decoder = decoder

    # def reparametrize(self, mu, std):
    #     if self.training:
    #         esp = Variable(std.data.new(std.size()).normal_(),
    #                        requires_grad=False).cuda()
    #         return mu + std * esp
    #     else:
    #         return mu

    def forward(self, x, nonlinearity=None):
        encoded = self.encoder(x)
        encoded = F.relu(encoded)
        # self.mu = self.mu_net(encoded)
        # self.std = self.logvar_net(encoded).exp_()
        # self.latent = self.reparametrize(self.mu, self.std)
        return self.decoder(None, nonlinearity=nonlinearity)


class ImageEncoder(ModelPlugin):
    '''Builds a simple image encoder.

    '''

    def build(self, encoder_type: str='convnet', dim_out: int=None,
              encoder_args=dict(fully_connected_layers=1028)):
        '''

        Args:
            encoder_type: Encoder model type.
            dim_out: Output size.
            encoder_args: Arguments for encoder build.

        '''
        x_shape = self.get_dims('x', 'y', 'c')
        Encoder, encoder_args = update_encoder_args(x_shape,
                                                    model_type=encoder_type,
                                                    encoder_args=encoder_args)
        encoder = Encoder(x_shape, dim_out=dim_out, **encoder_args)
        self.nets.encoder = encoder

    def encode(self, inputs, **kwargs):
        return self.nets.encoder(inputs, **kwargs)

    def visualize(self, inputs, targets):
        Z = self.encode(inputs)
        if targets is not None:
            targets = targets.data
        self.add_scatter(Z.data, labels=targets, name='latent values')


class ImageDecoder(ModelPlugin):
    '''Builds a simple image encoder.

    '''

    def build(self, decoder_type: str='convnet', dim_in: int=64,
              decoder_args=dict(output_nonlinearity='tanh')):
        '''

        Args:
            decoder_type: Decoder model type.
            dim_in: Input size.
            decoder_args: Arguments for the decoder.

        '''
        x_shape = self.get_dims('x', 'y', 'c')
        Decoder, decoder_args = update_decoder_args(x_shape,
                                                    model_type=decoder_type,
                                                    decoder_args=decoder_args)
        decoder = Decoder(x_shape, dim_in=dim_in, **decoder_args)
        self.nets.decoder = decoder

    def routine(self, inputs, Z, decoder_crit=F.mse_loss):
        '''

        Args:
            decoder_crit: Criterion for the decoder.

        '''

        X = self.decode(Z)
        self.losses.decoder = decoder_crit(X, inputs) / inputs.size(0)
        msssim = ms_ssim(inputs, X)
        self.results.ms_ssim = msssim.item()

    def decode(self, Z):
        return self.nets.decoder(Z)

    def visualize(self, Z):
        gen = self.decode(Z)
        self.add_image(gen, name='generated')


class AE(ModelPlugin):
    '''Variational autoencder.

    A generative model trained using the variational lower-bound to the
    log-likelihood.
    See: Kingma, Diederik P., and Max Welling.
    "Auto-encoding variational bayes." arXiv preprint arXiv:1312.6114 (2013).

    '''
    plugin_name = 'AE'

    defaults = dict(
        data=dict(batch_size=dict(train=64, test=640),
                  inputs=dict(inputs='images')),
        optimizer=dict(optimizer='Adam', learning_rate=1e-4),
        train=dict(save_on_lowest='losses.ae')
    )

    def __init__(self):
        super().__init__()

        encoder_contract = dict(kwargs=dict(dim_out='dim_encoder_out'))
        self.encoder = ImageEncoder(contract=encoder_contract)
        decoder_contract = dict(kwargs=dict(dim_in='dim_z'))
        self.decoder = ImageDecoder(contract=decoder_contract)

    def build(self, dim_z=64, dim_encoder_out=1028):
        '''

        Args:
            dim_z: Latent dimension.
            dim_encoder_out: Dimension of the final layer of the decoder before
                             decoding to mu and log sigma.

        '''
        self.encoder.build()
        self.decoder.build()

        self.add_noise('Z', dist='normal', size=dim_z)
        encoder = self.nets.encoder
        decoder = self.nets.decoder
        ae = AENetwork(encoder, decoder, dim_out=dim_encoder_out,
                         dim_z=dim_z)
        self.nets.ae = ae

    def routine(self, inputs, targets, Z, ae_criterion=F.mse_loss,
                beta_kld=1.):
        '''

        Args:
            ae_criterion: Reconstruction criterion.
            beta_kld: Beta scaling for KL term in lower-bound.

        '''
        ae = self.nets.ae
        outputs = ae(inputs)
        r_loss = ae_criterion(
            outputs, inputs, size_average=False) / inputs.size(0)
        # kl = (0.5 * (ae.std ** 2 + ae.mu ** 2 - 2. *
        #              torch.log(ae.std) - 1.).sum(1).mean())

        msssim = ms_ssim(inputs, outputs)

        self.losses.ae = r_loss
        # self.results.update(KL_divergence=kl.item(), ms_ssim=msssim.item())

    def visualize(self, inputs, targets):
        ae = self.nets.ae

        outputs = ae(inputs)

        self.add_image(outputs, name='reconstruction')
        self.add_image(inputs, name='ground truth')
        self.add_scatter(ae.mu.data, labels=targets.data, name='latent values')
        self.decoder.visualize(ae.mu.data)



if __name__ == '__main__':
    autoencoder = AE()
    run(model=autoencoder)

