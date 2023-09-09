from dotenv import load_dotenv
import aiohttp
import io
import os 
import av
import discord 
import uuid
import asyncio
from PIL import Image
from video_fetchers import sakugabooru
from discord import File
load_dotenv()

DISCORD_TOKEN = os.getenv('DISCORD_TOKEN')
class DiscordDataBot(discord.Bot):
    def __init__(self, start_frame=0, num_frames=96, gif_fps=20, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.user_history = {}
        self.waiting_for_input = {}
        self.waiting_for_edit = {}
        self.start_frame = start_frame
        self.num_frames = num_frames
        self.gif_fps = gif_fps
        self.gif_queue = asyncio.Queue()

    def get_params(self, random=False):
        # TODO: Do we need diversity and  randomness here?
        return self.start_frame, self.num_frames, self.gif_fps

    async def download_and_convert_to_gif(self, filename, input_url, start_frame=0, num_frames=96, gif_fps=24):
        # Download the video
        async with aiohttp.ClientSession() as session:
            async with session.get(input_url) as response:
                video_data = await response.read()

        # Convert the bytes to a file-like object
        video_buffer = io.BytesIO(video_data)
        container = av.open(video_buffer)
        video_stream = container.streams.video[0]

        # Process frames concurrently
        frames = self.decode_frames(container, video_stream, start_frame, num_frames)
        
        loop = asyncio.get_event_loop()
        def save_frames():
            frames[0].save(filename, 'GIF', append_images=frames[1:], save_all=True, duration=1000 / gif_fps, loop=0, optimize=True)

        await loop.run_in_executor(None, save_frames)

        return filename
    
    def decode_frames(self, container, video_stream, start_frame, num_frames):
        frames = []
        for i, frame in enumerate(container.decode(video_stream)):
            if i < start_frame:
                continue
            if i >= start_frame + num_frames:
                break
            image = frame.to_image()
            frames.append(image)
        return frames

class FeedbackView(discord.ui.View):
    def __init__(self, ctx, id, current_label = "", original_message_id = 0, labeled=False):
        super().__init__(timeout=1200)
        self.ctx = ctx
        self.id = id
        self.current_label = current_label
        self.original_message_id = original_message_id
        self.labeled = labeled

        #TODO: Is there a way to do callbacks with pycord without this ugly ass add_items? Why is callback not defined when I declare??

        # Check states and update the styles accordingly
        thumbs_value = self.ctx.bot.user_history[self.ctx.author.id][self.id]["rating"] if self.ctx.author.id in self.ctx.bot.user_history else 0
        thumbs_up_style = discord.ButtonStyle.success if thumbs_value == 1 else discord.ButtonStyle.secondary
        thumbs_down_style = discord.ButtonStyle.danger if thumbs_value == -1 else discord.ButtonStyle.secondary
        self.thumbs_up_button = discord.ui.Button(label="", emoji="👍", style=thumbs_up_style, row=0)
        self.thumbs_up_button.callback = self.thumbs_up
        self.add_item(self.thumbs_up_button)

        self.thumbs_down_button = discord.ui.Button(label="", emoji="👎", style=thumbs_down_style, row=0)
        self.thumbs_down_button.callback = self.thumbs_down
        self.add_item(self.thumbs_down_button)

        self.report_button = discord.ui.Button(label="", emoji="🚫", style=discord.ButtonStyle.secondary, row=0)
        self.report_button.callback = self.report
        self.add_item(self.report_button)

        if self.labeled:
            self.edit_button = discord.ui.Button(style=discord.ButtonStyle.secondary, label="", emoji="✏️", row=0)
            self.edit_button.callback = self.edit
            self.add_item(self.edit_button)
            self.delete_button = discord.ui.Button(style=discord.ButtonStyle.secondary, label="", emoji="🗑️", row=0)
            self.delete_button.callback = self.delete
            self.add_item(self.delete_button)
        else:
            self.skip_button = discord.ui.Button(style=discord.ButtonStyle.secondary, label="", emoji="⏭️", row=0)
            self.skip_button.callback = self.skip
            self.add_item(self.skip_button)

    async def edit(self, interaction: discord.Interaction):
        await interaction.response.defer()
        #Remove the user from waiting for input if they are trying to edit instead 
        if interaction.user.id in bot.waiting_for_input:
            del bot.waiting_for_input[interaction.user.id]
        await interaction.response.send_message(f"{interaction.user.mention}, please provide new text for this video/gif. \nYour current label: {self.current_label}")
        bot.waiting_for_edit[interaction.user.id] = {
            "ctx" : self.ctx, 
            "id" : self.id,
            "original_message_id": self.original_message_id
        }

    async def delete(self, interaction: discord.Interaction):
        await interaction.response.defer()
        if interaction.user.id in self.ctx.bot.user_history and self.id in self.ctx.bot.user_history[interaction.user.id]:
            del self.ctx.bot.user_history[interaction.user.id][self.id]
            await self.ctx.send(content=f"Deleted and removed label from dataset")
        await interaction.message.delete()

    async def skip(self, interaction: discord.Interaction):
        await interaction.response.send_message("Skipping gif, sending next one...")
        if interaction.user.id in bot.waiting_for_input:
            del bot.waiting_for_input[interaction.user.id]
        await send_gif(self.ctx) 

    async def thumbs_up(self, interaction: discord.Interaction):    
        await interaction.response.defer()

        # Change the style of thumbs up button and reset the thumbs down button
        self.thumbs_up_button.style = discord.ButtonStyle.success
        self.thumbs_down_button.style = discord.ButtonStyle.secondary
        await interaction.message.edit(view=self)
        bot.user_history[self.ctx.author.id][self.id]["rating"] = 1

    async def thumbs_down(self, interaction: discord.Interaction):
        await interaction.response.defer()

        # Change the style of thumbs down button and reset the thumbs up button
        self.thumbs_down_button.style = discord.ButtonStyle.danger
        self.thumbs_up_button.style = discord.ButtonStyle.secondary
        await interaction.message.edit(view=self)

        bot.user_history[self.ctx.author.id][self.id]["rating"] = -1

    async def report(self, interaction: discord.Interaction):
        await interaction.response.send_message("Video/GIF reported")
        await send_gif(self.ctx)

if __name__ == '__main__':
    intents = discord.Intents.default()
    intents.message_content = True 
    bot = DiscordDataBot(intents=intents)

    @bot.event
    async def on_ready():
        print(f"We have logged in as {bot.user}")
        bot.loop.create_task(fetch_and_process_gifs())

    async def fetch_and_process_gifs():
        while True:
            url = None
            gif_data = None
            if bot.gif_queue.qsize() < 10:
                filename = f"{uuid.uuid4()}.gif"                
                start_frame, num_frames, gif_fps = bot.get_params()
                url = sakugabooru.get_random_sakugabooru_video()
                if url:
                    await bot.download_and_convert_to_gif(filename, url, start_frame=start_frame, num_frames=num_frames, gif_fps=gif_fps)
                    try:
                        gif_data = Image.open(filename)
                    except Exception as e:
                        print(f"Failed to get gif: {e}")
                        gif_data = None
                if gif_data:
                    await asyncio.sleep(1)
                    await bot.gif_queue.put({
                        "filename": filename,
                        "url": url,
                        "start_frame" : start_frame, 
                        "num_frames" : num_frames, 
                        "fps" : gif_fps
                    })
            await asyncio.sleep(1)


    @bot.event
    async def on_message(message):
        if message.author == bot.user:
            return

        if message.author.id in bot.waiting_for_edit:
            ctx = bot.waiting_for_edit[message.author.id]["ctx"]
            id = bot.waiting_for_edit[message.author.id]["id"]
            original_message_id = bot.waiting_for_edit[message.author.id]["original_message_id"]
            del bot.waiting_for_edit[message.author.id]

            # Update the user's history with the new label
            original_label = ctx.bot.user_history[message.author.id][id]["label"]
            ctx.bot.user_history[message.author.id][id]["label"] = message.content
            original_msg = await ctx.channel.fetch_message(original_message_id)
            await original_msg.edit(content=f"Here's the updated video/GIF label\nYour label: {message.content}", view=FeedbackView(ctx, id, message.content, original_message_id, labeled=True))                
            await ctx.send(content=f"Updated label from {original_label} to --> {message.content}")
            await send_gif(ctx)

        elif message.author.id in bot.waiting_for_input:
            ctx = bot.waiting_for_input[message.author.id]["ctx"]
            original_message_id = bot.waiting_for_input[message.author.id]["message_id"]
            del bot.waiting_for_input[message.author.id]

            last_key = list(bot.user_history[ctx.author.id].keys())[-1]
            bot.user_history[ctx.author.id][last_key]["label"] = message.content
            id = bot.user_history[ctx.author.id][last_key]['id']

            # Switch to Edited Mode
            original_msg = await ctx.channel.fetch_message(original_message_id)
            await original_msg.edit(content=f"Here's the updated video/GIF label:\nYour label: {message.content}", view=FeedbackView(ctx, id, message.content, original_message_id, labeled=True))
            await send_gif(ctx)

    @bot.command(description="Labeling GIF")
    async def start_labeling(ctx):
        await ctx.respond("Fetching your gif... Please wait.")
        await send_gif(ctx)

    async def send_gif(ctx):
        id = f"{ctx.author.id}_{uuid.uuid4()}"
        gif = await bot.gif_queue.get()
        filename = gif["filename"]
        if not gif:
            await ctx.send("Sorry, I couldn't fetch a random GIF.")
            return

        if ctx.author.id not in bot.user_history:
            bot.user_history[ctx.author.id] = {}

        bot.user_history[ctx.author.id][id] = {
            "id": id,
            "url": gif["url"],
            "label": "",
            "rating": 0,
            "start_frame": gif["start_frame"],
            "fps": gif["fps"], 
            "num_frames": gif["num_frames"]
        }

        message = await ctx.send(
            content=f"{ctx.author.mention}, please type in the chat a description of what's happening in this video/gif", 
            file=File(filename, filename=f"{id}.gif"), 
            view=FeedbackView(ctx, id=id)
        )        
        bot.waiting_for_input[ctx.author.id] = {"ctx": ctx, "message_id": message.id}
        await asyncio.sleep(1)
        os.remove(filename)

    print("Running...")
    bot.run(DISCORD_TOKEN)