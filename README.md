# PDF Extractor

Aplicação web para extrair texto selecionável de arquivos PDF e exportar o resultado em TXT, JSON ou PDF.

## Subir localmente com Docker

O compose usa a rede externa `coolify`, igual ao ambiente de produção. Para testar fora do Coolify, crie a rede uma única vez:

```bash
docker network create coolify
docker compose -f docker-compose.yml -f docker-compose.local.yml up --build
```

Abra `http://127.0.0.1:3000`. A API fica em `http://127.0.0.1:8000`.

## Publicar no Coolify

1. Crie um recurso do tipo Docker Compose apontando para este repositório.
2. Aponte o domínio do frontend para o serviço `web`, porta `3000`.
3. Aponte o domínio da API para o serviço `api`, porta `8000`.
4. Configure `NEXT_PUBLIC_API_URL` com a URL pública da API e faça o deploy.

A rede externa `coolify` já existe nas instalações padrão. Os serviços também compartilham uma rede privada entre si.

Os PDFs são processados em memória e não são mantidos em disco. O limite por upload é de 25 MB. PDFs apenas com imagens exigem OCR e retornam uma mensagem explicativa.
