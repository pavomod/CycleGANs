import tensorflow as tf
from models import make_generator_model, make_discriminator_model, CycleGAN
from data_loader import load_mnist,load_robotics_data, add_salt_pepper_noise,save_models,load_models,remove_pixel
from utils import *
import numpy as np
from tqdm import tqdm
from loss import generator_loss, discriminator_loss, cycle_consistency_loss, identity_loss
from params import EPOCHS, BATCH_SIZE, TRAIN_IMAGES, VAL_IMAGES, TEST_IMAGES, LAMBDA_CYCLE, LEARNING_RATE_GEN, LEARNING_RATE_DISC,BETA, SAVE_EVERY_TRAIN, SAVE_EVERY_TEST, VALIDATION_EVERY

def test_model(model, test_dataset, num_images=5, plot=True,epoch=0):
    '''
    Tests the model on a given test dataset, calculates the average losses, and optionally plots and saves images. 
    Uses a progress bar to show testing progress.

    Parameters:
        model (CycleGAN): The CycleGAN model to be tested.
        test_dataset (tf.data.Dataset): The dataset to test the model on.
        num_images (int): Number of images to plot from each batch.
        plot (bool): Whether to plot images during testing.
        epoch (int): The current epoch number, used for saving images.

    Returns:
        dict: A dictionary containing the average losses for the generators and discriminators.
    '''
    test_losses = []
    #use tqdm to show progress bar
    for batch, (image_batch, noisy_batch) in enumerate(tqdm(test_dataset, desc=f"Epoch {epoch}")):
        generated_images = model.generator_G(noisy_batch, training=False)
        generated_images = generated_images.numpy()
        if plot:
            plot_images(image_batch.numpy(), noisy_batch.numpy(), generated_images, num_images=num_images)
        data = (image_batch, noisy_batch)
        test_loss = model.test_step(data)
        test_losses.append(test_loss)
        if batch % SAVE_EVERY_TEST == 0:
            save_images(image_batch.numpy(), noisy_batch.numpy(), generated_images, epoch, str(batch),output_dir="test_images")
    avg_G_loss = np.mean([loss['G_loss'] for loss in test_losses])
    avg_F_loss = np.mean([loss['F_loss'] for loss in test_losses])
    avg_DX_loss = np.mean([loss['D_X_loss'] for loss in test_losses])
    avg_DY_loss = np.mean([loss['D_Y_loss'] for loss in test_losses])

    print("Average Generator G Loss:", avg_G_loss)
    print("Average Generator F Loss:", avg_F_loss)
    print("Average Discriminator X Loss:", avg_DX_loss)
    print("Average Discriminator Y Loss:", avg_DY_loss)
    print("\n\n")
    return {
        "avg_G_loss": avg_G_loss,
        "avg_F_loss": avg_F_loss,
        "avg_DX_loss": avg_DX_loss,
        "avg_DY_loss": avg_DY_loss
    }



def run(resume_train=False,start_epoch=0,robotics_task=False,shape=(28,28,1)):
    '''
    Sets up and runs the training loop for the CycleGAN model, optionally resuming from a specified epoch.
    Handles the creation or loading of models, optimizers, and datasets. Performs training, validation, 
    and testing while saving model weights and images at specified intervals.

    Parameters:
        resume_train (bool): Whether to resume training from a saved checkpoint.
        start_epoch (int): The epoch to start/resume training from.
        robotics_task (bool): Flag indicating if the task is related to robotics (affects data loading).
        shape (tuple): The shape of the input images.

    Returns:
        None
    '''
    physical_devices = tf.config.list_physical_devices('GPU')
    print("GPUs:", physical_devices)
    device = '/gpu:0' if tf.config.list_physical_devices('GPU') else '/cpu:0'
    print('Using device:', device)

    with tf.device(device):
        if resume_train and robotics_task==False:
            try:
                gen_G, gen_F, disc_X, disc_Y = load_models(start_epoch)
                print(f"===================== Resuming training from epoch {start_epoch+1} ===================== ")
            except Exception as e:
                print(f"Error loading models: {e}")
                print(" ===================== Starting training from scratch. ===================== ")
                start_epoch = 0
                gen_G = make_generator_model(shape)
                gen_F = make_generator_model(shape)
                disc_X = make_discriminator_model(shape)
                disc_Y = make_discriminator_model(shape)
        else:
            gen_G = make_generator_model(shape)
            gen_F = make_generator_model(shape)
            disc_X = make_discriminator_model(shape)
            disc_Y = make_discriminator_model(shape)
        
        g_optimizer = tf.keras.optimizers.Adam(2e-4, beta_1=0.5)
        d_optimizer = tf.keras.optimizers.Adam(1e-4, beta_1=0.5)


        cycle_gan_model = CycleGAN(gen_G, gen_F, disc_X, disc_Y, lambda_cycle=LAMBDA_CYCLE)
        cycle_gan_model.compile(
            g_optimizer=g_optimizer,
            d_optimizer=d_optimizer,
            gen_loss_fn=generator_loss,
            disc_loss_fn=discriminator_loss,
            cycle_loss_fn=cycle_consistency_loss,
            identity_loss_fn=identity_loss
        )

        if robotics_task==False:
            train_images, val_images, test_images = load_mnist(TRAIN_IMAGES, VAL_IMAGES, TEST_IMAGES)
            noisy_train_images = add_salt_pepper_noise(train_images)
            noisy_val_images = add_salt_pepper_noise(val_images)
            noisy_test_images = add_salt_pepper_noise(test_images)
        else:
            train_images, val_images, test_images = load_robotics_data()
            noisy_train_images = remove_pixel(train_images)
            noisy_val_images = remove_pixel(val_images)
            noisy_test_images = remove_pixel(test_images)


        train_dataset = tf.data.Dataset.from_tensor_slices((train_images, noisy_train_images)).batch(BATCH_SIZE)
        val_dataset = tf.data.Dataset.from_tensor_slices((val_images, noisy_val_images)).batch(BATCH_SIZE)
        test_dataset = tf.data.Dataset.from_tensor_slices((test_images, noisy_test_images)).batch(BATCH_SIZE)

        #PLOT THE FIRST 5 IMAGES OF TRAIN, VAL AND TEST
        plot_images(train_images[:5], noisy_train_images[:5], train_images[:5], num_images=5)
        plot_images(val_images[:5], noisy_val_images[:5], val_images[:5], num_images=5)
        plot_images(test_images[:5], noisy_test_images[:5], test_images[:5], num_images=5)

        train_g_losses = []
        train_f_losses = []
        train_dx_losses = []
        train_dy_losses = []

        val_g_losses = []
        val_f_losses = []
        val_dx_losses = []
        val_dy_losses = []

        # dimensione train
        print("Train images shape: ",train_images.shape)
        print("Noisy Train images shape: ",noisy_train_images.shape)

        print("===================== Training =====================\n")
        for epoch in range(start_epoch,EPOCHS):  
            print(f"===================== Epoch {epoch+1} =====================\n")
            for batch, (image_batch, noisy_batch) in enumerate(tqdm(train_dataset, desc=f"Epoch {epoch+1}")):
                data = (image_batch, noisy_batch)
                train_loss = cycle_gan_model.train_step(data)
                train_g_losses.append(train_loss["G_loss"].numpy())
                train_f_losses.append(train_loss["F_loss"].numpy())
                train_dx_losses.append(train_loss["D_X_loss"].numpy())
                train_dy_losses.append(train_loss["D_Y_loss"].numpy())

                if batch % SAVE_EVERY_TRAIN == 0:  # Save images every 100 batches
                    generated_images = cycle_gan_model.generator_G(noisy_batch, training=False)
                    save_images(image_batch.numpy(), noisy_batch.numpy(), generated_images.numpy(), epoch, batch,output_dir="train_images")
                if batch % VALIDATION_EVERY == 0 and batch != 0:
                    print("===================== Validation  LOSS =====================\n")
                    avg_val_loss = test_model(cycle_gan_model, val_dataset, num_images=5, plot=False,epoch=str(epoch)+"_"+str(batch))
                    val_g_losses.append(avg_val_loss["avg_G_loss"])
                    val_f_losses.append(avg_val_loss["avg_F_loss"])
                    val_dx_losses.append(avg_val_loss["avg_DX_loss"])
                    val_dy_losses.append(avg_val_loss["avg_DY_loss"])              
            train_g_losses.append(train_loss["G_loss"].numpy())
            train_f_losses.append(train_loss["F_loss"].numpy())
            train_dx_losses.append(train_loss["D_X_loss"].numpy())
            train_dy_losses.append(train_loss["D_Y_loss"].numpy())

            print("\n===================== saving models for epoch: "+ str(epoch+1)+" =====================\n")
            save_models(cycle_gan_model.generator_G, cycle_gan_model.generator_F, cycle_gan_model.discriminator_X, cycle_gan_model.discriminator_Y, epoch)
            print(f"===================== Epoch {epoch+1} complete =====================\n\n")

        print("\n\n===================== Test LOSS =====================\n")
        test_model(cycle_gan_model, test_dataset, num_images=5, plot=False,epoch="final_test")
        print("\n\n===================== Training complete =====================\n\n")

        

def load_model_and_only_test(epoch=1):
    '''
    Loads a CycleGAN model from a specified epoch checkpoint and performs testing on the MNIST test dataset.
    Compiles the model with predefined optimizers and loss functions, applies salt and pepper noise to the 
    test images, and evaluates the model's performance.

    Parameters:
        epoch (int): The epoch number to load the model from.

    Returns:
        None
    '''
    gen_G, gen_F, disc_X, disc_Y = load_models(epoch=epoch)
    g_optimizer = tf.keras.optimizers.Adam(LEARNING_RATE_GEN, beta_1=BETA)
    d_optimizer = tf.keras.optimizers.Adam(LEARNING_RATE_DISC, beta_1=BETA)

    cycle_gan_model = CycleGAN(
        generator_G=gen_G, 
        generator_F=gen_F, 
        discriminator_X=disc_X, 
        discriminator_Y=disc_Y, 
        lambda_cycle=LAMBDA_CYCLE
    )
    
    cycle_gan_model.compile(
        g_optimizer=g_optimizer,
        d_optimizer=d_optimizer,
        gen_loss_fn=generator_loss,
        disc_loss_fn=discriminator_loss,
        cycle_loss_fn=cycle_consistency_loss,
        identity_loss_fn=identity_loss
    )
    
    _, _, test_images = load_mnist(TRAIN_IMAGES, VAL_IMAGES, TEST_IMAGES)
    noisy_test_images = add_salt_pepper_noise(test_images)
    test_dataset = tf.data.Dataset.from_tensor_slices((test_images, noisy_test_images)).batch(BATCH_SIZE)
    
    print("\n\n===================== Test =====================\n")
    test_model(cycle_gan_model, test_dataset, num_images=5, plot=False, epoch="final_test")
    print("\n\n===================== Testing complete =====================\n\n")

