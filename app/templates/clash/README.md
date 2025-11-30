# Clash Template

## Usage

- Can be used to send completely prepared config to users depend on your usage.

## Config Template

- With the config template, you can change things like routing and rules.

## How To Use

First of all, you need to set a directory for all of your templates (home, subscription page, etc.).

```shell
CUSTOM_TEMPLATES_DIRECTORY="/var/lib/pasarguard/templates/"
```

Make sure you put all of your templates in this folder.\
If you are using Docker, make sure Docker has access to this folder.\
Then, we need to make a directory for our Clash template.

```shell
mkdir -p /var/lib/pasarguard/templates/clash
```

After that, put your templates (config and settings) in the directory.\
Now, change these variables with your files' names.

```shell
CLASH_SUBSCRIPTION_TEMPLATE = "clash/default.yml"
```

Now, restart your PasarGuard and enjoy.

If you have already changed your env variables, and you want to just update the template files, there is no need to restart PasarGuard.

## Docs

you can use these docs to find out how to modify template files

[Mihomo Docs](https://wiki.metacubex.one/en/)
