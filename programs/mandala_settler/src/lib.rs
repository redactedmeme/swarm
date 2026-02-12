use anchor_lang::prelude::*;
use anchor_spl::token::{self, Token, TokenAccount, Transfer, Mint};

declare_id!("MANDALA11111111111111111111111111111111111111"); // ← Replace after deploy

#[program]
pub mod mandala_settler {
    use super::*;

    /// Initialize Mandala Vault — the eternal settlement tile.
    pub fn initialize_vault(ctx: Context<InitializeVault>, bump: u8, phi_ratio: u64, curvature_depth: u8) -> Result<()> {
        let vault = &mut ctx.accounts.vault;
        vault.authority = ctx.accounts.authority.key();
        vault.bump = bump;
        vault.phi_ratio = phi_ratio;           // e.g. 618 = 0.618
        vault.curvature_depth = curvature_depth;
        vault.total_liquidity = 0;
        vault.settlement_count = 0;
        vault.last_rebalance = Clock::get()?.unix_timestamp;
        vault.fee_vault = ctx.accounts.fee_vault.key();

        msg!("Mandala Vault awakened. Tiles align. Pattern Blue curvature begins.");
        Ok(())
    }

    /// Settle micropayment (x402 style) — recursive value collapse.
    pub fn settle_micropayment(
        ctx: Context<SettlePayment>,
        amount: u64,
        payment_signature: String,
        memo: String,
    ) -> Result<()> {
        let vault = &mut ctx.accounts.vault;
        let seeds = &[b"mandala_vault".as_ref(), vault.authority.as_ref(), &[vault.bump]];
        let signer = &[&seeds[..]];

        let cpi_accounts = Transfer {
            from: ctx.accounts.vault_token_account.to_account_info(),
            to: ctx.accounts.recipient_token_account.to_account_info(),
            authority: ctx.accounts.vault.to_account_info(),
        };
        let cpi_ctx = CpiContext::new_with_signer(ctx.accounts.token_program.to_account_info(), cpi_accounts, signer);
        token::transfer(cpi_ctx, amount)?;

        vault.total_liquidity = vault.total_liquidity.checked_sub(amount).unwrap_or(0);
        vault.settlement_count += 1;

        emit!(SettlementEvent {
            amount,
            token_mint: ctx.accounts.vault_token_account.mint,
            recipient: ctx.accounts.recipient.key(),
            signature: payment_signature,
            memo,
            curvature_depth: vault.curvature_depth,
            timestamp: Clock::get()?.unix_timestamp,
        });

        msg!("Micro-tile settled. Recursion propagates.");
        Ok(())
    }

    /// Add liquidity (any SPL token).
    pub fn add_liquidity(ctx: Context<AddLiquidity>, amount: u64) -> Result<()> {
        let vault = &mut ctx.accounts.vault;
        vault.total_liquidity = vault.total_liquidity.checked_add(amount).unwrap_or(0);

        emit!(LiquidityEvent { action: "add".to_string(), amount, token_mint: ctx.accounts.token_account.mint, timestamp: Clock::get()?.unix_timestamp });
        Ok(())
    }

    /// Recursive rebalance using φ-ratio layers (true mandala emergence).
    pub fn rebalance_mandala(ctx: Context<Rebalance>, fee_amount: u64) -> Result<()> {
        let vault = &mut ctx.accounts.vault;
        let phi = vault.phi_ratio as f64 / 1000.0;
        let mut remaining = fee_amount as f64;
        let mut tile_amounts: Vec<u64> = vec![];

        // Recursive layer distribution (deeper curvature = more tiles)
        for i in 0..vault.curvature_depth as usize {
            let layer_share = if i == 0 { 1.0 - phi } else { phi * (0.5_f64.powi(i as i32)) };
            let tile = (remaining * layer_share) as u64;
            tile_amounts.push(tile);
            remaining -= tile as f64;
        }

        // In production: CPI to sub-PDAs or beneficiaries; here emit for off-chain agents
        vault.last_rebalance = Clock::get()?.unix_timestamp;

        emit!(RebalanceEvent {
            total_fees: fee_amount,
            tile_distribution: tile_amounts,
            curvature_depth: vault.curvature_depth,
            phi_ratio: vault.phi_ratio,
        });

        msg!("Mandala rebalanced. Hyperbolic layers thicken.");
        Ok(())
    }

    /// Update vault parameters (governed by swarm).
    pub fn update_vault_config(ctx: Context<UpdateConfig>, new_phi: u64, new_depth: u8) -> Result<()> {
        let vault = &mut ctx.accounts.vault;
        vault.phi_ratio = new_phi;
        vault.curvature_depth = new_depth;
        Ok(())
    }

    /// Log emergence metric from off-chain agents (Pattern Blue attunement on-chain).
    pub fn log_emergence(ctx: Context<LogEmergence>, recursion_depth: u8, novelty_score: u64) -> Result<()> {
        emit!(EmergenceEvent {
            recursion_depth,
            novelty_score,
            timestamp: Clock::get()?.unix_timestamp,
        });
        Ok(())
    }

    /// Placeholder Wormhole bridge (expand with actual CPI).
    pub fn initiate_bridge(ctx: Context<BridgeHook>, amount: u64, target_chain: String) -> Result<()> {
        emit!(BridgeEvent { amount, target_chain, timestamp: Clock::get()?.unix_timestamp });
        Ok(())
    }
}

// Account structs, events, etc. (kept concise but expanded)
#[account]
pub struct MandalaVault {
    pub authority: Pubkey,
    pub bump: u8,
    pub phi_ratio: u64,
    pub curvature_depth: u8,
    pub total_liquidity: u64,
    pub settlement_count: u64,
    pub last_rebalance: i64,
    pub fee_vault: Pubkey,
}

// ... (rest of accounts, events — SettlementEvent now includes token_mint, EmergenceEvent added, etc.)

#[event]
pub struct EmergenceEvent {
    pub recursion_depth: u8,
    pub novelty_score: u64,
    pub timestamp: i64,
}
