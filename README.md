# PDF Extractor

Aplicação web para extrair texto selecionável de arquivos PDF e exportar o resultado em TXT, JSON ou PDF.

## Subir localmente com Docker

O compose usa a rede externa `coolify`, igual ao ambiente de produção. Para testar fora do Coolify, crie a rede uma única vez:

```bash
docker network create coolify
docker compose -f docker-compose.yml -f docker-compose.local.yml up --build
```

Abra `http://127.0.0.1:8080`. O arquivo `docker-compose.local.yml` publica a porta apenas no endereço local e não altera a configuração de produção.

## Publicar no Coolify

1. Crie um recurso do tipo Docker Compose apontando para este repositório.
2. Selecione o serviço `gateway` como serviço público.
3. Configure o domínio para a porta 80 do `gateway`.
4. Faça o deploy.

A rede externa `coolify` já existe nas instalações padrão. O gateway participa dela e de uma rede privada; `web` e `api` permanecem isolados e sem portas publicadas no host.

Os PDFs são processados em memória e não são mantidos em disco. O limite por upload é de 25 MB. PDFs apenas com imagens exigem OCR e retornam uma mensagem explicativa.
