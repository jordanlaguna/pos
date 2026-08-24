<script lang="ts">
	import { enhance } from '$app/forms';
	import { submit } from '$lib/ui/forms';
	import Icon from '$lib/ui/components/Icon.svelte';
	import PageHeader from '$lib/ui/components/PageHeader.svelte';
	import Modal from '$lib/ui/components/Modal.svelte';
	import Field from '$lib/ui/components/Field.svelte';
	import EmptyState from '$lib/ui/components/EmptyState.svelte';
	import { m } from '$lib/paraglide/messages.js';
	import type { Category } from '$lib/domain/types';
	import type { ActionData, PageData } from './$types';

	let { data, form }: { data: PageData; form: ActionData } = $props();

	/** La madre del alta en curso. Nulo es una raíz nueva. */
	let creatingUnder = $state<Category | null>(null);
	let createOpen = $state(false);
	let renaming = $state<Category | null>(null);
	let moving = $state<Category | null>(null);
	let deleting = $state<Category | null>(null);

	let fName = $state('');
	let fParent = $state('');

	const products = $derived((id: number) => data.productCount[id] ?? 0);
	const roots = $derived(data.tree.map((branch) => branch.root));

	function openCreate(parent: Category | null) {
		creatingUnder = parent;
		fName = '';
		createOpen = true;
	}

	function openRename(category: Category) {
		renaming = category;
		fName = category.name;
	}

	function openMove(category: Category) {
		moving = category;
		fParent = category.parent_id === null ? '' : String(category.parent_id);
	}
</script>

<PageHeader title={m.categories_title()} description={m.categories_description()}>
	{#snippet actions()}
		<a href="/inventario" class="btn btn-ghost">
			<Icon name="box" size={15} />
			{m.categories_back_to_inventory()}
		</a>
		<button type="button" class="btn btn-primary" onclick={() => openCreate(null)}>
			<Icon name="plus" size={15} />
			{m.categories_new_root()}
		</button>
	{/snippet}
</PageHeader>

<p class="mb-4 text-xs text-[var(--text-subtle)]">{m.categories_two_levels_note()}</p>

{#if data.tree.length === 0}
	<div class="card p-6">
		<EmptyState
			icon="tag"
			title={m.categories_empty()}
			description={m.categories_empty_hint()}
			compact
		/>
	</div>
{/if}

<div class="grid gap-3">
	{#each data.tree as branch, indice (branch.root.id)}
		<section class="card p-3">
			<!-- ------------------------------------------------------- la raíz -->
			<div class="flex flex-wrap items-center gap-2">
				<div class="flex flex-col">
					<form method="POST" action="?/ordenar" use:enhance={submit({ quiet: true })}>
						<input type="hidden" name="id" value={branch.root.id} />
						<input type="hidden" name="direction" value="up" />
						<button
							type="submit"
							class="rounded p-0.5 text-[var(--text-subtle)] hover:text-[var(--accent)] disabled:opacity-30"
							disabled={indice === 0}
							aria-label={m.categories_move_up({ category: branch.root.name })}
						>
							<Icon name="up" size={14} />
						</button>
					</form>
					<form method="POST" action="?/ordenar" use:enhance={submit({ quiet: true })}>
						<input type="hidden" name="id" value={branch.root.id} />
						<input type="hidden" name="direction" value="down" />
						<button
							type="submit"
							class="rounded p-0.5 text-[var(--text-subtle)] hover:text-[var(--accent)] disabled:opacity-30"
							disabled={indice === data.tree.length - 1}
							aria-label={m.categories_move_down({ category: branch.root.name })}
						>
							<Icon name="down" size={14} />
						</button>
					</form>
				</div>

				<Icon name="tag" size={15} />
				<p class="font-semibold text-[var(--text)]">{branch.root.name}</p>

				{#if !branch.root.is_active}
					<span class="badge bg-[var(--surface-sunken)] text-[var(--text-muted)]">
						{m.categories_inactive()}
					</span>
				{/if}
				{#if branch.children.length > 0}
					<span class="badge bg-[var(--surface-sunken)] text-[var(--text-muted)]">
						{m.categories_children_count({ count: branch.children.length })}
					</span>
				{:else}
					<span class="badge bg-[var(--surface-sunken)] text-[var(--text-muted)]">
						{m.categories_products_count({ count: products(branch.root.id) })}
					</span>
				{/if}

				<div class="ml-auto flex items-center gap-1">
					<button
						type="button"
						class="btn btn-ghost"
						onclick={() => openCreate(branch.root)}
					>
						<Icon name="plus" size={14} />
						{m.categories_new_child()}
					</button>
					<button
						type="button"
						class="rounded-lg p-1.5 text-[var(--text-subtle)] hover:bg-[var(--surface-sunken)] hover:text-[var(--accent)]"
						onclick={() => openRename(branch.root)}
						aria-label={m.categories_rename_label({ category: branch.root.name })}
					>
						<Icon name="edit" size={15} />
					</button>
					<form method="POST" action="?/estado" use:enhance={submit()}>
						<input type="hidden" name="id" value={branch.root.id} />
						<input type="hidden" name="is_active" value={branch.root.is_active ? 'false' : 'true'} />
						<button
							type="submit"
							class="rounded-lg p-1.5 text-[var(--text-subtle)] hover:bg-[var(--surface-sunken)] hover:text-[var(--accent)]"
							aria-label={branch.root.is_active
								? m.categories_deactivate_label({ category: branch.root.name })
								: m.categories_activate_label({ category: branch.root.name })}
						>
							<Icon name={branch.root.is_active ? 'eyeoff' : 'eye'} size={15} />
						</button>
					</form>
					<button
						type="button"
						class="rounded-lg p-1.5 text-[var(--text-subtle)] hover:bg-[var(--negative-bg)] hover:text-[var(--negative)]"
						onclick={() => (deleting = branch.root)}
						aria-label={m.categories_delete_label({ category: branch.root.name })}
					>
						<Icon name="trash" size={15} />
					</button>
				</div>
			</div>

			<!-- --------------------------------------------- las subcategorías -->
			{#if branch.children.length > 0}
				<ul class="mt-2 space-y-1 border-l border-[var(--border)] pl-4">
					{#each branch.children as child, posicion (child.id)}
						<li class="flex flex-wrap items-center gap-2 py-1">
							<div class="flex flex-col">
								<form method="POST" action="?/ordenar" use:enhance={submit({ quiet: true })}>
									<input type="hidden" name="id" value={child.id} />
									<input type="hidden" name="direction" value="up" />
									<button
										type="submit"
										class="rounded p-0.5 text-[var(--text-subtle)] hover:text-[var(--accent)] disabled:opacity-30"
										disabled={posicion === 0}
										aria-label={m.categories_move_up({ category: child.name })}
									>
										<Icon name="up" size={12} />
									</button>
								</form>
								<form method="POST" action="?/ordenar" use:enhance={submit({ quiet: true })}>
									<input type="hidden" name="id" value={child.id} />
									<input type="hidden" name="direction" value="down" />
									<button
										type="submit"
										class="rounded p-0.5 text-[var(--text-subtle)] hover:text-[var(--accent)] disabled:opacity-30"
										disabled={posicion === branch.children.length - 1}
										aria-label={m.categories_move_down({ category: child.name })}
									>
										<Icon name="down" size={12} />
									</button>
								</form>
							</div>

							<p class="text-sm text-[var(--text)]">{child.name}</p>
							{#if !child.is_active}
								<span class="badge bg-[var(--surface-sunken)] text-[var(--text-muted)]">
									{m.categories_inactive()}
								</span>
							{/if}
							<span class="badge bg-[var(--surface-sunken)] text-[var(--text-muted)]">
								{m.categories_products_count({ count: products(child.id) })}
							</span>

							<div class="ml-auto flex items-center gap-1">
								<button
									type="button"
									class="rounded-lg p-1.5 text-[var(--text-subtle)] hover:bg-[var(--surface-sunken)] hover:text-[var(--accent)]"
									onclick={() => openRename(child)}
									aria-label={m.categories_rename_label({ category: child.name })}
								>
									<Icon name="edit" size={14} />
								</button>
								<button
									type="button"
									class="rounded-lg p-1.5 text-[var(--text-subtle)] hover:bg-[var(--surface-sunken)] hover:text-[var(--accent)]"
									onclick={() => openMove(child)}
									aria-label={m.categories_move_label({ category: child.name })}
								>
									<Icon name="forward" size={14} />
								</button>
								<form method="POST" action="?/estado" use:enhance={submit()}>
									<input type="hidden" name="id" value={child.id} />
									<input type="hidden" name="is_active" value={child.is_active ? 'false' : 'true'} />
									<button
										type="submit"
										class="rounded-lg p-1.5 text-[var(--text-subtle)] hover:bg-[var(--surface-sunken)] hover:text-[var(--accent)]"
										aria-label={child.is_active
											? m.categories_deactivate_label({ category: child.name })
											: m.categories_activate_label({ category: child.name })}
									>
										<Icon name={child.is_active ? 'eyeoff' : 'eye'} size={14} />
									</button>
								</form>
								<button
									type="button"
									class="rounded-lg p-1.5 text-[var(--text-subtle)] hover:bg-[var(--negative-bg)] hover:text-[var(--negative)]"
									onclick={() => (deleting = child)}
									aria-label={m.categories_delete_label({ category: child.name })}
								>
									<Icon name="trash" size={14} />
								</button>
							</div>
						</li>
					{/each}
				</ul>
			{/if}
		</section>
	{/each}
</div>

<!-- ------------------------------------------------------------- alta -->
<Modal
	open={createOpen}
	title={creatingUnder ? m.categories_new_child() : m.categories_new_root()}
	description={creatingUnder ? m.categories_child_of({ category: creatingUnder.name }) : undefined}
	size="sm"
	onclose={() => (createOpen = false)}
>
	<form
		id="category-create"
		method="POST"
		action="?/crear"
		use:enhance={submit({ onSuccess: () => (createOpen = false) })}
	>
		<input type="hidden" name="parent_id" value={creatingUnder?.id ?? ''} />
		<Field
			label={m.categories_label_name()}
			name="name"
			bind:value={fName}
			required
			placeholder={creatingUnder
				? m.categories_child_placeholder()
				: m.categories_root_placeholder()}
			error={form?.errors?.name}
		/>
	</form>

	{#snippet footer()}
		<button type="button" class="btn btn-ghost" onclick={() => (createOpen = false)}>
			{m.common_cancel()}
		</button>
		<button type="submit" form="category-create" class="btn btn-primary">
			<Icon name="check" size={15} />
			{m.common_create()}
		</button>
	{/snippet}
</Modal>

<!-- --------------------------------------------------------- renombrar -->
<Modal
	open={renaming !== null}
	title={m.categories_rename_title()}
	description={renaming?.name}
	size="sm"
	onclose={() => (renaming = null)}
>
	<form
		id="category-rename"
		method="POST"
		action="?/renombrar"
		use:enhance={submit({ onSuccess: () => (renaming = null) })}
	>
		<input type="hidden" name="id" value={renaming?.id ?? ''} />
		<Field
			label={m.categories_label_name()}
			name="name"
			bind:value={fName}
			required
			error={form?.errors?.name}
		/>
	</form>

	{#snippet footer()}
		<button type="button" class="btn btn-ghost" onclick={() => (renaming = null)}>
			{m.common_cancel()}
		</button>
		<button type="submit" form="category-rename" class="btn btn-primary">
			<Icon name="check" size={15} />
			{m.common_save_changes()}
		</button>
	{/snippet}
</Modal>

<!-- ------------------------------------------------------------- mover -->
<Modal
	open={moving !== null}
	title={m.categories_move_title()}
	description={moving?.name}
	size="sm"
	onclose={() => (moving = null)}
>
	<form
		id="category-move"
		method="POST"
		action="?/mover"
		use:enhance={submit({ onSuccess: () => (moving = null) })}
	>
		<input type="hidden" name="id" value={moving?.id ?? ''} />
		<label class="label" for="category-parent">{m.categories_label_parent()}</label>
		<select id="category-parent" name="parent_id" bind:value={fParent} class="input">
			<option value="">{m.categories_parent_root()}</option>
			{#each roots as root (root.id)}
				{#if root.id !== moving?.id}
					<option value={String(root.id)} selected={String(root.id) === fParent}>
						{root.name}
					</option>
				{/if}
			{/each}
		</select>
		<p class="mt-2 text-xs text-[var(--text-subtle)]">{m.categories_move_hint()}</p>
	</form>

	{#snippet footer()}
		<button type="button" class="btn btn-ghost" onclick={() => (moving = null)}>
			{m.common_cancel()}
		</button>
		<button type="submit" form="category-move" class="btn btn-primary">
			<Icon name="check" size={15} />
			{m.categories_move()}
		</button>
	{/snippet}
</Modal>

<!-- ------------------------------------------------------------ borrar -->
<Modal
	open={deleting !== null}
	title={m.categories_delete_title()}
	size="sm"
	onclose={() => (deleting = null)}
>
	<p class="text-sm text-[var(--text-muted)]">
		{m.categories_delete_confirm({ category: deleting?.name ?? '' })}
	</p>
	<p class="mt-2 text-xs text-[var(--text-subtle)]">{m.categories_delete_note()}</p>

	{#snippet footer()}
		<button type="button" class="btn btn-ghost" onclick={() => (deleting = null)}>
			{m.common_cancel()}
		</button>
		<form
			method="POST"
			action="?/borrar"
			use:enhance={submit({ onSuccess: () => (deleting = null) })}
		>
			<input type="hidden" name="id" value={deleting?.id ?? ''} />
			<button type="submit" class="btn btn-danger">
				<Icon name="trash" size={15} />
				{m.common_delete()}
			</button>
		</form>
	{/snippet}
</Modal>
