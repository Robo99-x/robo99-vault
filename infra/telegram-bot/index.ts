import { Bot } from "grammy";

const BOT_TOKEN = process.env.BOT_TOKEN;
if (!BOT_TOKEN) {
  console.error("BOT_TOKEN 환경변수가 설정되지 않았습니다.");
  process.exit(1);
}

const bot = new Bot(BOT_TOKEN);

bot.command("start", (ctx) => {
  ctx.reply(
    `안녕하세요! ${ctx.from?.first_name ?? ""}님\n\n` +
    `사용 가능한 명령어:\n` +
    `/start - 봇 시작\n` +
    `/help - 도움말\n` +
    `/ping - 연결 확인`
  );
});

bot.command("help", (ctx) => {
  ctx.reply("도움이 필요하시면 메시지를 보내주세요!");
});

bot.command("ping", (ctx) => {
  ctx.reply("Pong!");
});

bot.on("message:text", (ctx) => {
  ctx.reply(`받은 메시지: "${ctx.message.text}"`);
});

bot.catch((err) => {
  console.error("봇 에러:", err);
});

bot.start();
console.log("텔레그램 봇이 시작되었습니다!");