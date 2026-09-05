</div>

<!-- Mobilde görünen alt sekme menüsü (bottom navigation) -->
<nav class="md:hidden fixed bottom-0 inset-x-0 bg-white border-t border-slate-200 shadow-[0_-4px_16px_rgba(0,0,0,0.05)] z-30">
    <div class="grid grid-cols-7">
        <?php foreach ($__nav_items as $item): $aktif = $__mevcut_sayfa === $item['match']; ?>
        <a href="<?= $item['href'] ?>"
           class="flex flex-col items-center justify-center gap-1 py-2.5 <?= $aktif ? 'text-amber-600' : 'text-slate-400' ?>">
            <?php if ($item['match'] === 'index.php'): ?>
                <svg class="w-6 h-6" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="<?= $aktif ? '2.5' : '2' ?>">
                    <path stroke-linecap="round" stroke-linejoin="round" d="M3 13h4v8H3v-8zM10 3h4v18h-4V3zM17 9h4v12h-4V9z" />
                </svg>
            <?php elseif ($item['match'] === 'musteriler.php'): ?>
                <svg class="w-6 h-6" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="<?= $aktif ? '2.5' : '2' ?>">
                    <path stroke-linecap="round" stroke-linejoin="round" d="M17 20h5v-2a4 4 0 00-3-3.87M9 20H4v-2a4 4 0 013-3.87m6-1.13a4 4 0 100-8 4 4 0 000 8zm6-2a2.5 2.5 0 10-2-4.5" />
                </svg>
            <?php elseif ($item['match'] === 'gunluk_giris.php'): ?>
                <svg class="w-6 h-6" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="<?= $aktif ? '2.5' : '2' ?>">
                    <path stroke-linecap="round" stroke-linejoin="round" d="M8 7V3m8 4V3m-9 8h10M5 21h14a2 2 0 002-2V7a2 2 0 00-2-2H5a2 2 0 00-2 2v12a2 2 0 002 2z" />
                </svg>
            <?php else: ?>
                <svg class="w-6 h-6" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="<?= $aktif ? '2.5' : '2' ?>">
                    <path stroke-linecap="round" stroke-linejoin="round" d="M12 6v6h4m6 0a10 10 0 11-20 0 10 10 0 0120 0z" />
                </svg>
            <?php endif; ?>
            <span class="text-[10px] font-medium leading-tight text-center"><?= $item['label'] ?></span>
        </a>
        <?php endforeach; ?>
    </div>
</nav>

</body>
</html>
