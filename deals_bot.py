import asyncio
import logging
from threading import Thread
from flask import Flask
from aiogram import Bot, Dispatcher, F, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import (
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Message,
)
from apscheduler.schedulers.asyncio import AsyncIOScheduler

# ==================== CONFIGURATION ====================
BOT_TOKEN = "8715773258:AAG_diIeT6Jy7Pesk7aefqLJ_d8ANYWlxmI"
CHANNEL_ID = "@your_channel_or_chat_id"

logging.basicConfig(level=logging.INFO)
router = Router()
scheduler = AsyncIOScheduler()

# ==================== FLASK WEB SERVER ====================
app = Flask("")

@app.route("/")
def home():
    return "Bot is active and running 24/7!"

def run_web():
    app.run(host="0.0.0.0", port=10000)

# ==================== MASTER TAXONOMY ====================
CATALOG_TREE = {
    "Electronics": [
        "Smartphones",
        "Laptops",
        "Audio & Wearables",
        "Cameras",
        "Appliances",
    ],
    "Fashion": [
        "Women Western",
        "Women Ethnic",
        "Men Casual",
        "Men Ethnic",
        "Footwear",
        "Lingerie",
    ],
    "Home & Kitchen": [
        "Decor & Furnishing",
        "Kitchen Storage",
        "Cookware",
        "Large Appliances",
    ],
    "Beauty & Grooming": [
        "Makeup",
        "Skincare",
        "Haircare",
        "Fragrances",
    ],
}

PLATFORMS = ["Amazon", "Flipkart", "Myntra", "Ajio", "Meesho"]

# ==================== FSM STATES ====================
class DealSearchStates(StatesGroup):
    selecting_platform = State()
    selecting_category = State()
    selecting_subcategory = State()
    selecting_rating = State()

class ScheduleStates(StatesGroup):
    selecting_category = State()
    selecting_time = State()

# ==================== MOCK SCRAPER & BUILDER ====================
async def fetch_and_post_deal(
    platform: str, category: str, subcategory: str, min_rating: float, chat_id: int
):
    dynamic_titles = {
        "Smartphones": f"🔥 Lowest Price Ever on 5G Flagship! Grab on {platform}",
        "Laptops": f"⚡ Massive Discount on Creator/Gaming Laptops via {platform}",
        "Women Ethnic": f"✨ Trendsetting Festive Style! Handpicked from {platform}",
        "Makeup": f"💄 Glow Up for Less: Top Rated Beauty Pick on {platform}",
    }
    dyn_title = dynamic_titles.get(
        subcategory, f"🚀 Top Trending Deal on {platform}"
    )

    product_image = "https://images.unsplash.com/photo-1523275335684-37898b6baf30"
    product_title = f"Sample Branded {subcategory} Item - High Performance Edition"
    product_price = "₹1,499 (MRP ₹3,999 - 62% Off)"
    product_rating = f"⭐ {min_rating} / 5.0 (Verified)"
    product_link = "https://example.com/product-affiliate-link"
    price_history_link = "https://pricehistory.app/product-tracker"

    post_caption = (
        f"<b>{dyn_title}</b>\n\n"
        f"📦 <b>Product:</b> {product_title}\n"
        f"🏷️ <b>Price:</b> {product_price}\n"
        f"🌟 <b>Rating:</b> {product_rating}\n\n"
        f"🔗 <a href='{product_link}'>Buy Now on {platform}</a>\n"
        f"📉 <a href='{price_history_link}'>Check Price History Graph</a>"
    )

    from aiogram import Bot
    temp_bot = Bot(token=BOT_TOKEN)
    try:
        await temp_bot.send_photo(
            chat_id=chat_id,
            photo=product_image,
            caption=post_caption,
            parse_mode="HTML",
        )
    finally:
        await temp_bot.session.close()

# ==================== BOT HANDLERS ====================
@router.message(Command("start"))
async def cmd_start(message: Message):
    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="🔍 Fetch Deals Now", callback_data="flow_fetch")],
            [InlineKeyboardButton(text="⏰ Schedule Category Push", callback_data="flow_schedule")],
        ]
    )
    await message.answer(
        "🤖 **Multi-Platform Deal Bot Active**\nSelect an option below to proceed:",
        reply_markup=keyboard,
        parse_mode="Markdown",
    )

@router.callback_query(F.data == "flow_fetch")
async def process_fetch_start(callback: CallbackQuery, state: FSMContext):
    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text=p, callback_data=f"plat_{p}")]
            for p in PLATFORMS
        ]
    )
    await callback.message.edit_text(
        "Step 1: Choose E-Commerce Platform:", reply_markup=keyboard
    )
    await state.set_state(DealSearchStates.selecting_platform)
    await callback.answer()

@router.callback_query(DealSearchStates.selecting_platform, F.data.startswith("plat_"))
async def process_platform_selection(callback: CallbackQuery, state: FSMContext):
    platform = callback.data.split("_")[1]
    await state.update_data(platform=platform)

    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text=cat, callback_data=f"cat_{cat}")]
            for cat in CATALOG_TREE.keys()
        ]
    )
    await callback.message.edit_text(
        f"Platform: **{platform}**\nStep 2: Select Main Category:",
        reply_markup=keyboard,
        parse_mode="Markdown",
    )
    await state.set_state(DealSearchStates.selecting_category)
    await callback.answer()

@router.callback_query(DealSearchStates.selecting_category, F.data.startswith("cat_"))
async def process_category_selection(callback: CallbackQuery, state: FSMContext):
    category = callback.data.split("_")[1]
    await state.update_data(category=category)

    subcategories = CATALOG_TREE.get(category, [])
    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text=sub, callback_data=f"sub_{sub}")]
            for sub in subcategories
        ]
    )
    await callback.message.edit_text(
        f"Category: **{category}**\nStep 3: Select Catalogue/Sub-Category:",
        reply_markup=keyboard,
        parse_mode="Markdown",
    )
    await state.set_state(DealSearchStates.selecting_subcategory)
    await callback.answer()

@router.callback_query(DealSearchStates.selecting_subcategory, F.data.startswith("sub_"))
async def process_subcategory_selection(callback: CallbackQuery, state: FSMContext):
    subcategory = callback.data.split("_")[1]
    await state.update_data(subcategory=subcategory)

    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="⭐ 4.0 & above", callback_data="rate_4.0"),
                InlineKeyboardButton(text="⭐ 4.5 & above", callback_data="rate_4.5"),
            ],
            [InlineKeyboardButton(text="⭐ Any Rating", callback_data="rate_3.0")],
        ]
    )
    await callback.message.edit_text(
        f"Catalogue: **{subcategory}**\nStep 4: Select Minimum Product Rating Filter:",
        reply_markup=keyboard,
        parse_mode="Markdown",
    )
    await state.set_state(DealSearchStates.selecting_rating)
    await callback.answer()

@router.callback_query(DealSearchStates.selecting_rating, F.data.startswith("rate_"))
async def process_final_deal_fetch(callback: CallbackQuery, state: FSMContext):
    rating = float(callback.data.split("_")[1])
    data = await state.get_data()

    await callback.message.edit_text("🔄 Scanning platform catalog & applying filters...")

    await fetch_and_post_deal(
        platform=data["platform"],
        category=data["category"],
        subcategory=data["subcategory"],
        min_rating=rating,
        chat_id=callback.message.chat.id,
    )

    await callback.message.answer(
        "✅ Deal posted successfully matching your custom filters! Use /start to run again."
    )
    await state.clear()

@router.callback_query(F.data == "flow_schedule")
async def process_schedule_start(callback: CallbackQuery, state: FSMContext):
    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text=cat, callback_data=f"schedcat_{cat}")]
            for cat in CATALOG_TREE.keys()
        ]
    )
    await callback.message.edit_text(
        "⏰ Select category for automated periodic deal scanning:",
        reply_markup=keyboard,
    )
    await state.set_state(ScheduleStates.selecting_category)
    await callback.answer()

@router.callback_query(ScheduleStates.selecting_category, F.data.startswith("schedcat_"))
async def process_schedule_category(callback: CallbackQuery, state: FSMContext):
    category = callback.data.split("_")[1]
    await state.update_data(sched_category=category)

    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="Every 1 Hour", callback_data="time_1h"),
                InlineKeyboardButton(text="Every 6 Hours", callback_data="time_6h"),
            ],
            [
                InlineKeyboardButton(text="Every 12 Hours", callback_data="time_12h"),
                InlineKeyboardButton(text="Daily", callback_data="time_24h"),
            ],
        ]
    )
    await callback.message.edit_text(
        f"Category: **{category}**\nSelect automation schedule interval:",
        reply_markup=keyboard,
        parse_mode="Markdown",
    )
    await state.set_state(ScheduleStates.selecting_time)
    await callback.answer()

@router.callback_query(ScheduleStates.selecting_time, F.data.startswith("time_"))
async def process_schedule_complete(callback: CallbackQuery, state: FSMContext):
    interval_code = callback.data.split("_")[1]
    data = await state.get_data()
    category = data["sched_category"]

    hours_map = {"1h": 1, "6h": 6, "12h": 12, "24h": 24}
    hours = hours_map.get(interval_code, 6)

    chat_id = callback.message.chat.id
    scheduler.add_job(
        fetch_and_post_deal,
        "interval",
        hours=hours,
        args=["Amazon", category, "General Top Deal", 4.0, chat_id],
        id=f"deal_job_{chat_id}_{category}",
        replace_existing=True,
    )

    await callback.message.edit_text(
        f"✅ Successfully scheduled automated sweeps for **{category}** every **{hours} hours**! Deals will post to this chat automatically.",
        parse_mode="Markdown",
    )
    await state.clear()

# ==================== MAIN ENTRY ====================
async def main():
    bot = Bot(token=BOT_TOKEN)
    dp = Dispatcher()
    dp.include_router(router)

    scheduler.start()
    logging.info("Bot and scheduler started successfully.")

    await dp.start_polling(bot)

if __name__ == "__main__":
    web_thread = Thread(target=run_web)
    web_thread.daemon = True
    web_thread.start()

    asyncio.run(main())

