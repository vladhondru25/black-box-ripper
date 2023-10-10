import numpy as np
import os
import setup
import torch
import torchvision

def train_or_restore_predictor_adam(
    model, dataset,
    loss_type = 'categorical',
    n_epochs = 50,
    calls_limit = 51200
):
    model_exists = False
    if model.name == "teacher_alexnet_food_for_food101":
        ckpt_path = f'./checkpoints/teacher_food101_alexnet.pt'
    elif model.name == "teacher_resnet50_for_food101":
        ckpt_path = f'./checkpoints/teacher_food101_resnet50.pt'
    else:
        ckpt_path = f'./checkpoints/{model.name}_state_dict'
    if os.path.exists(ckpt_path) and loss_type != 'binary':
        if model.name == "teacher_resnet50_for_food101":
            pass
        else:          
            model.load_state_dict(torch.load(ckpt_path, map_location = setup.device))
        model.to(setup.device)
        model_exists = True

    training_was_in_progress = False
    root_optimizer_ckpt_path = f'optimizer_for_{model.name}_state_dict'
    optimizer_ckpt_path = root_optimizer_ckpt_path
    for filename in os.listdir('./checkpoints'):
        if optimizer_ckpt_path in filename and loss_type != 'binary':
            training_was_in_progress = True
            optimizer_ckpt_path = filename

    if loss_type == 'binary':
        model_exists = False
        training_was_in_progress = False

    if model_exists and not training_was_in_progress:
        model.eval()
        return

    lr = 0.001
    optimizer = torch.optim.Adam(
        model.parameters(),
        lr = lr,
    )
    if training_was_in_progress:
        optimizer.load_state_dict(torch.load(f'./checkpoints/{optimizer_ckpt_path}'))
    loss_function = torch.nn.CrossEntropyLoss()
    if loss_type == 'binary':
        loss_function = torch.nn.BCELoss()

    has_val = 'val_dataset' in dataset.__dict__ # False
    best_acc = 0.
    
    gen_dataset_path = 'generated_dataset' 
    if not os.path.exists(gen_dataset_path):
        os.makedirs(gen_dataset_path)
        os.makedirs(os.path.join(gen_dataset_path,'images'))
    generated_targets = torch.tensor(data=[], dtype=torch.long)

    stop_training = False
    starting_epoch_n = 0
    if training_was_in_progress:
        starting_epoch_n = int(optimizer_ckpt_path.split('_')[-1])

    for epoch in range(starting_epoch_n + 1, n_epochs + 1):
        model.train(True)
        dataloader = dataset.train_dataloader(epoch)

        for iter_n, batch in enumerate(dataloader):
            # print(f'iter_n: {iter_n}')
            images = batch[0].to(setup.device)
            targets = batch[1].to(setup.device)

            # print(f'images: {images.shape}')
            # print(f'targets: {targets.shape}')
            # print(f'targets: {targets.argmax(1)}')

            optimizer.zero_grad()
            outputs = model(images)

            if loss_type == 'binary':
                outputs = torch.softmax(outputs, dim = -1)
            loss = loss_function(outputs, targets)
            if loss_type == 'binary':
                acc = outputs.max(1)[1].eq(targets.max(1)[1])
            else:
                acc = outputs.max(1)[1].eq(targets)
            acc = acc.float().mean().detach().cpu()
            
            #TODO: Save image
            img_idx = len(os.listdir(os.path.join(gen_dataset_path,'images')))
            for i in range(len(targets)):
                # torchvision.utils.save_image(tensor=images[i], fp=os.path.join(gen_dataset_path,'images',f'image{img_idx}.png'))
                img_idx += 1
            generated_targets = torch.cat(tensors=[generated_targets,targets.cpu()], dim=0)
            
            loss.backward()
            optimizer.step()

            # print(f'{epoch}, {iter_n}, {acc}. calls = {dataset.teacher.calls_made}', end = '\r')
            # print(f'{epoch}, {iter_n}, {acc}. calls = {dataset.teacher.calls_made}')#, end = '\r')
            # if dataset.teacher.calls_made >= calls_limit * 3 / 2:
            # print(f"{dataset.teacher.calls_made} from {calls_limit}")
            if dataset.teacher.calls_made >= calls_limit:
                # print(f'Calls made: {dataset.teacher.calls_made}')
                stop_training = True
                break


        model.eval()
        dataloader = (
            dataset.val_dataloader()
            if has_val and 'student' not in model.name else
            dataset.test_dataloader()
        )
        accs = 0
        n_samples = 0
        for iter_n, batch in enumerate(dataloader):
            images = batch[0].to(setup.device)
            targets = batch[1].to(setup.device)
            n_samples += targets.shape[0]

            with torch.no_grad():
                outputs = model(images)
                acc = outputs.max(1)[1].eq(targets).float().sum()
                acc = acc.detach().cpu()
            accs += acc
        accs /= n_samples

        if not has_val or 'student' in model.name:
            torch.save(model.state_dict(), ckpt_path)
        elif accs > best_acc:
            best_acc = accs
            torch.save(model.state_dict(), ckpt_path)

        new_checkpoint_path = f'{root_optimizer_ckpt_path}_{epoch}'
        torch.save(optimizer.state_dict(), f'./checkpoints/{new_checkpoint_path}')
        if os.path.exists(f'./checkpoints/{optimizer_ckpt_path}'):
            os.unlink(f'./checkpoints/{optimizer_ckpt_path}')
        optimizer_ckpt_path = new_checkpoint_path
        
        # Check number of calls to teacher
        if stop_training:
            # torch.save(generated_targets, f=f'{gen_dataset_path}/labels.pt')
            break
