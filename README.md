# PDF Extractor

Aplicação web para extrair texto selecionável de arquivos PDF e exportar o resultado em TXT, JSON ou PDF. A interface também oferece a leitura estruturada dos laudos de controle de qualidade em JSON. O contrato está documentado em [docs/structured-extraction.md](docs/structured-extraction.md).

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

## Testar a extração estruturada

Com a API rodando em `http://127.0.0.1:8000`, envie um dos exemplos:

```bash
curl -sS -X POST http://127.0.0.1:8000/api/extract/structured \
  -F 'file=@examples/2556.pdf' | jq .
```

O endpoint retorna JSON com os campos do cabeçalho e uma ou mais tabelas. Ele reconhece as duas tabelas presentes nos exemplos e tolera diferenças de maiúsculas, acentos, espaços e quebras de linha. Veja o contrato, os exemplos completos e o uso em Python em [docs/structured-extraction.md](docs/structured-extraction.md).

Para verificar o frontend, abra `http://127.0.0.1:3000`, escolha o modo “Laudo estruturado (JSON)”, envie `examples/2556.pdf`, `examples/laudo.pdf`, `examples/1353.pdf` ou `examples/3555.pdf` e clique em “Extrair laudo estruturado”.
