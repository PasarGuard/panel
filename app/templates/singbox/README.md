# Sing-box Template

## Usage

- Can be used to send completely prepared config to users depend on your usage.

## Config Template

- With the config template, you can change things like routing and rules.

## How To Use

First of all, you need to set a directory for all of your templates (home, subscription page, etc.).

```shell
CUSTOM_TEMPLATES_DIRECTORY="/var/lib/marzban/templates/"
```

Make sure you put all of your templates in this folder.\
If you are using Docker, make sure Docker has access to this folder.\
Then, we need to make a directory for our Sing-box template.

```shell
mkdir /var/lib/marzban/templates/sing-box
```

After that, put your templates (config and settings) in the directory.\
Now, change these variables with your files' names.

```shell
SINGBOX_SUBSCRIPTION_TEMPLATE="singbox/default.json"
```

Now, restart your Marzban and enjoy.

If you have already changed your env variables, and you want to just update the template files, there is no need to restart Marzban.

## Docs

you can use sing-box official documentation to find out how to modify template files

[Sing-Box documentation](https://sing-box.sagernet.org/configuration/)
